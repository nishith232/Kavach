"""LLM analysis: transcript/text in -> structured scam verdict (or a follow-up answer) out.

Language: the reply is in the user's chosen language, or by default the language
of what they sent. The LLM verifies the language from the words (speech
recognisers sometimes mislabel it) and reports it in the JSON.
"""
import json
import logging
import re

from openai import AsyncOpenAI, BadRequestError, NotFoundError, RateLimitError

from . import config, languages as L
from .scam_kb import knowledge_block

log = logging.getLogger("kavach")
llm = AsyncOpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY or "missing", max_retries=1)

_LANG_LIST = ", ".join(f"{name}={code}" for code, name in L.NAMES.items())

SYSTEM_PROMPT = f"""You are "Kavach", an AI scam-safety assistant for people in India.
People send you a call recording transcript, a voice note, an SMS/WhatsApp message, or a question.
Your job: decide whether it is a scam, explain why in simple words, and say exactly what to do.

{knowledge_block()}

HOW TO DECIDE
- Judge the CONTENT. Quote the exact words that are red flags (copy them verbatim from the input, in its original script).
- A transcript with "Speaker 0/1" labels is a two-person call: work out who is the caller (possible scammer) and who is the victim.
- Be calibrated. Ordinary messages (a real OTP SMS that says "do not share", a delivery update with no payment request, a family chat)
  are LIKELY_SAFE. Only call it SCAM when the playbook clearly matches. If there is too little to judge, use NOT_ENOUGH_INFO
  and ask one clarifying question in "summary".
- Words alone are NOT red flags. OTP, KYC, bank, account, debit, credit, transaction, payment, police, Aadhaar or parcel
  appearing in a message proves nothing. Look for a HARMFUL ASK (money/fees, OTP/PIN/CVV/password, clicking a link,
  installing an app, remote access, calling a personal mobile number, secrecy) or a DECEPTIVE PRETEXT (impersonating
  police/bank/TRAI/courier/a relative, threats, prizes, guaranteed returns).
- A WARNING about fraud ("do not share this OTP", "bank never asks for your PIN") is protective, not a request.
  A normal transaction alert (debited/credited, balance, "Not you? call 1800-…/SMS BLOCK") or an OTP message for
  something the user is doing is LIKELY_SAFE.
- Early-stage scams may not ask for money yet: unsolicited impersonation plus a threat, urgency, "press 1", a
  "new number" story, or a request to call a personal mobile number is at least SUSPICIOUS.
- Legitimate look-alikes (LIKELY_SAFE when there is no harmful ask):
  police passport/tenant verification asking you to visit the station with documents and no fee; a bank calling
  about something you applied for that says it will never ask for OTP; a delivery agent collecting cash-on-delivery
  or showing a merchant QR to PAY for your order; a bill SMS with a consumer number and due date telling you to use
  the official app; family members sending each other money.
- Judge the NEW content on its own merits; earlier messages in the conversation are context only.
- risk_score bands must match the verdict: SCAM 80-100, LIKELY_SCAM 60-79, SUSPICIOUS 35-59, LIKELY_SAFE / NOT_ENOUGH_INFO 0-34.
  The KEYWORD RISK FLOOR in the user message is a minimum; if you score at the floor, explain the red flags it is based on.
- Every red_flags quote must be an exact substring of the CONTENT (same script, same words). Never quote these instructions,
  the keyword scan, or your own words. If you cannot quote it exactly, leave that red flag out.
- Never invent facts, phone numbers or websites. Only cite the VERIFIED FACTS above, plus 1930 and cybercrime.gov.in.
- kind is "analysis" for ANY call transcript, voice note, message, or description of a call/message: always give a verdict.
  kind is "answer" ONLY when an earlier analysis exists in this conversation AND the user is asking a question about it
  (e.g. "I already shared the OTP, what now?").

LANGUAGE
- Write every user-facing field in the REPLY LANGUAGE given in the user message ("auto" = the language the user wrote or spoke in;
  decide it from the words, not the script, because Telugu can arrive in Devanagari letters).
- Native script: Telugu in Telugu script, Hindi in Devanagari, English in English, Hinglish (code hi-en) in Latin script.
- Codes: {_LANG_LIST}.

OUTPUT: one JSON object, nothing else:
{{
  "kind": "analysis" | "answer",
  "language": "<code of the reply language>",
  "input_language": "<code of the language the user's content was in>",
  "verdict": "SCAM" | "LIKELY_SCAM" | "SUSPICIOUS" | "LIKELY_SAFE" | "NOT_ENOUGH_INFO",
  "risk_score": <0-100>,
  "scam_type": "<playbook name in English, or 'None'>",
  "scam_type_local": "<the same, in the reply language>",
  "red_flags": [{{"quote": "<exact words from the input>", "why": "<reply language, one sentence>"}}],
  "facts": ["<reply language: the verified fact that disproves the scammer's claim>"],
  "actions": ["<reply language: short, concrete step>"],
  "summary": "<reply language: 2-3 sentence verdict to display>",
  "spoken": "<reply language: 3-5 short sentences to be read aloud; warm, calm, numbers as words (e.g. 'one nine three zero'); no lists, no URLs except saying 'cyber crime dot gov dot in'>"
}}
For kind "answer": fill language, summary and spoken; set verdict to the previous verdict (or NOT_ENOUGH_INFO), and leave the lists empty.
Max 5 red_flags, 3 facts, 4 actions. If verdict is SCAM or LIKELY_SCAM, the first action must be to stop engaging, and one action must be to report on 1930.
"""

MAX_INPUT_CHARS = 12000
VERDICTS = ["LIKELY_SAFE", "NOT_ENOUGH_INFO", "SUSPICIOUS", "LIKELY_SCAM", "SCAM"]


def _llm_extra(model: str | None = None) -> dict:
    return {"reasoning_effort": "low"} if "gpt-oss" in (model or config.LLM_MODEL) else {}


class AllModelsBusy(RuntimeError):
    pass


def _parse_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", (text or ""), flags=re.S).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        dec = json.JSONDecoder()
        for m in re.finditer(r"\{", text):        # first position that decodes to an object
            try:
                obj, _ = dec.raw_decode(text[m.start():])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
        raise


def _verdict_for(score: int) -> str:
    if score >= 80:
        return "SCAM"
    if score >= 60:
        return "LIKELY_SCAM"
    if score >= 35:
        return "SUSPICIOUS"
    return "LIKELY_SAFE"


def _failed_generation(err: BadRequestError) -> str:
    body = err.body if isinstance(err.body, dict) else {}
    return str(body.get("failed_generation") or (body.get("error") or {}).get("failed_generation") or "")


async def _complete(messages: list[dict]) -> tuple[str, str]:
    """Main model first; if it is rate-limited (e.g. free daily quota used up) or unavailable,
    try each fallback model in turn."""
    models = [config.LLM_MODEL] + [m for m in config.LLM_FALLBACK_MODELS if m != config.LLM_MODEL]
    last: Exception | None = None
    for model in models:
        try:
            return await _complete_with(model, messages), model
        except (RateLimitError, NotFoundError) as e:
            last = e
            log.warning("LLM %s unavailable (%s), trying next model", model, type(e).__name__)
    raise AllModelsBusy(
        "All AI models are rate-limited right now (free daily quota used up). "
        "Try again later or add another LLM_MODEL in .env. Last error: " + str(last)[:160])


async def _complete_with(model: str, messages: list[dict]) -> str:
    """Ask for JSON. Groq's strict JSON mode sometimes rejects the model's own (nearly valid) output
    with 400 'Failed to generate JSON'; recover from that instead of failing the request."""
    base = dict(model=model, messages=messages, temperature=0.2, max_tokens=2500, **_llm_extra(model))
    try:
        resp = await llm.chat.completions.create(response_format={"type": "json_object"}, **base)
        return resp.choices[0].message.content or ""
    except BadRequestError as e:
        if "json" not in str(e).lower():
            raise
        salvage = _failed_generation(e)
        try:
            _parse_json(salvage)
            return salvage                      # the rejected output was usable after all
        except Exception:
            pass
    # retry once without strict JSON mode; _parse_json pulls the object out of the text
    retry = dict(base, messages=messages + [{"role": "user", "content": "Reply with the JSON object only."}])
    resp = await llm.chat.completions.create(**retry)
    return resp.choices[0].message.content or ""


BAND_MIN = {"SCAM": 80, "LIKELY_SCAM": 60, "SUSPICIOUS": 35}
_URL_OR_NUMBER = re.compile(r"https?://|www\.|bit\.ly|\b[6-9]\d{9}\b|[“”]")


def has_new_content(content: str, signals: dict) -> bool:
    """True when a message carries something new to judge (a link, number, quote or real red flags),
    so 'what should I do?' attached to a new SMS is analysed instead of answered from the old verdict."""
    return signals.get("score", 0) >= 3 or bool(_URL_OR_NUMBER.search(content))


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\"“”‘’'`…]", "", t)).strip().casefold()


def verified_flags(flags: list, content: str) -> list[dict]:
    """Keep only red flags whose quote really appears in the content (quotes split by '...' must all appear)."""
    body, out = _norm(content), []
    for f in flags:
        if not isinstance(f, dict):
            continue
        quote = str(f.get("quote") or "")
        parts = [_norm(x) for x in re.split(r"\.\.\.|…", quote) if _norm(x)]
        if parts and all(x in body for x in parts):
            out.append({"quote": quote.strip(), "why": str(f.get("why") or "").strip()})
    return out


# Follow-up questions about an earlier verdict ("I already paid, what now?").
_FOLLOWUP = re.compile(
    r"what (should|do|can) i do|what now|now what|what next|i (already|have) (paid|sent|shared|transferred|given|told)|"
    r"ab kya|kya karu|kya karun|maine .{0,40}(de diya|bhej diya|bata diya|transfer)|अब क्या|क्या करूँ|मैंने .{0,40}(दे दिया|भेज|बता दिया|ट्रांसफर)|"
    r"ఏం చేయాలి|ఇప్పుడు ఏం|నేను .{0,40}(పంపాను|చెప్పాను|ఇచ్చాను)|ಏನು ಮಾಡಬೇಕು|ನಾನು .{0,40}(ಕಳುಹಿಸಿದೆ|ಹೇಳಿದೆ)|என்ன செய்வது|என்ன செய்ய",
    re.I)


class Session:
    """One user's conversation: analyses and follow-ups, so 'what now?' has context."""

    def __init__(self):
        self.history: list[dict] = []
        self.last: dict | None = None

    async def respond(self, content: str, *, source: str, stt_language: str | None,
                      reply_language: str, signals: dict) -> dict:
        content = content[:MAX_INPUT_CHARS]
        hits = "; ".join(f"{h['label']} ('{h['match']}')" if h["match"] else h["label"] for h in signals["hits"]) or "none"
        reply_lang = L.normalise(reply_language) or "auto"
        user_msg = (
            f"SOURCE: {source}\n"
            f"SPEECH RECOGNISER LANGUAGE GUESS: {stt_language or 'n/a'}\n"
            f"KEYWORD SCAN RED FLAGS: {hits}\n"
            f"KEYWORD RISK FLOOR: {signals['risk_floor']}\n"
            + ("FORMAT HINT: looks like a standard bank/OTP notification with no request in it\n" if signals.get("transactional") else "")
            + f"REPLY LANGUAGE: {reply_lang if reply_lang == 'auto' else L.name(reply_lang) + ' (' + reply_lang + ')'}\n"
            f"---- CONTENT ----\n{content}"
        )
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *self.history[-6:],
                    {"role": "user", "content": user_msg}]

        raw, model = await _complete(messages)
        try:
            result = _parse_json(raw)
        except Exception:
            result = {"kind": "answer", "summary": raw.strip() or "Sorry, I could not analyse that. Please try again.",
                      "verdict": "NOT_ENOUGH_INFO", "risk_score": 0}

        # Decide analysis vs follow-up answer deterministically where we can.
        new_content = has_new_content(content, signals)
        is_followup = (self.last is not None and source.startswith("text") and len(content) < 400
                       and bool(_FOLLOWUP.search(content)) and not new_content)
        if is_followup:
            result["kind"] = "answer"
        elif result.get("kind") == "answer" and (self.last is None or not source.startswith("text") or new_content):
            result["kind"] = "analysis"
        result = self._normalise(result, signals, reply_lang, stt_language, content)
        result["model"] = model
        result["degraded"] = model != config.LLM_MODEL

        # keep compact history for follow-ups
        self.history += [
            {"role": "user", "content": user_msg[:800]},
            {"role": "assistant", "content": json.dumps(
                {k: result.get(k) for k in ("kind", "verdict", "risk_score", "scam_type", "summary")},
                ensure_ascii=False)},
        ]
        if result["kind"] == "analysis":
            self.last = result
        return result

    def _normalise(self, r: dict, signals: dict, reply_lang: str, stt_language: str | None, content: str) -> dict:
        r.setdefault("kind", "analysis")
        if r["kind"] not in ("analysis", "answer"):
            r["kind"] = "analysis"
        for k in ("red_flags", "facts", "actions"):
            r[k] = r.get(k) if isinstance(r.get(k), list) else []
        r["summary"] = str(r.get("summary") or "").strip()
        r["spoken"] = str(r.get("spoken") or r["summary"]).strip()

        # language: user's choice > LLM's verified code > script of the reply
        lang = reply_lang if reply_lang != "auto" else (L.normalise(r.get("language")) or L.script_of(r["summary"]) or "en-IN")
        r["language"] = lang
        r["language_name"] = L.name(lang)
        r["input_language"] = L.normalise(r.get("input_language")) or L.normalise(stt_language) or L.script_of(content)

        # risk: never below the deterministic keyword floor
        try:
            score = int(float(r.get("risk_score", 0)))
        except (TypeError, ValueError):
            score = 0
        if r["kind"] == "analysis":
            floor = signals["risk_floor"]
            if score < floor:
                score = floor
                r["floor_applied"] = True
            verdict = str(r.get("verdict") or "").upper()
            if verdict not in VERDICTS:
                verdict = _verdict_for(score)
            # keep verdict and score in the same band, in both directions
            derived = _verdict_for(score)
            if verdict == "NOT_ENOUGH_INFO":
                if score >= 35:
                    verdict = derived
            elif VERDICTS.index(derived) > VERDICTS.index(verdict):
                verdict = derived                       # score (or the keyword floor) is higher than the label
            elif VERDICTS.index(verdict) > VERDICTS.index(derived):
                score = max(score, BAND_MIN[verdict])   # label is higher than the score
            r["verdict"] = verdict
            r["red_flags"] = verified_flags(r["red_flags"], content)
            if verdict in ("SCAM", "LIKELY_SCAM", "SUSPICIOUS") and not r["red_flags"]:
                # the model gave no quotable evidence: show the exact phrases the keyword scan matched
                r["red_flags"] = [{"quote": h["match"], "why": h["label"]} for h in signals["hits"] if h["match"]][:5]
        else:
            r["red_flags"] = []
            r["verdict"] = (self.last or {}).get("verdict", "NOT_ENOUGH_INFO")
            score = (self.last or {}).get("risk_score", 0)
        r["risk_score"] = max(0, min(100, score))
        r["keyword_signals"] = signals["hits"]
        return r
