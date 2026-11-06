"""LLM analysis: transcript/text in -> structured scam verdict (or a follow-up answer) out.

Language: the reply is in the user's chosen language, or by default the language
of what they sent. The LLM verifies the language from the words (speech
recognisers sometimes mislabel it) and reports it in the JSON.
"""
import json
import re

from openai import AsyncOpenAI, BadRequestError

from . import config, languages as L
from .scam_kb import knowledge_block

llm = AsyncOpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY or "missing")

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
- A scam needs a HARMFUL ASK: money/fees, OTP/PIN/CVV, a link or app install, remote access, secrecy, or personal
  details under threat or time pressure. If there is NO harmful ask, it is LIKELY_SAFE (or NOT_ENOUGH_INFO),
  even when police, banks, Aadhaar, parcels or payments are mentioned. Legitimate look-alikes:
  police passport/tenant verification asking you to visit the station with documents and no fee; a bank calling
  about something you applied for that says it will never ask for OTP; a delivery agent collecting cash-on-delivery
  or showing a merchant QR to PAY for your order; a bill SMS with a consumer number and due date telling you to use
  the official app; family members sending each other money.
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


def _llm_extra() -> dict:
    return {"reasoning_effort": "low"} if "gpt-oss" in config.LLM_MODEL else {}


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
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


async def _complete(messages: list[dict]) -> str:
    """Ask for JSON. Groq's strict JSON mode sometimes rejects the model's own (nearly valid) output
    with 400 'Failed to generate JSON'; recover from that instead of failing the request."""
    base = dict(model=config.LLM_MODEL, messages=messages, temperature=0.2, max_tokens=2500, **_llm_extra())
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
            f"REPLY LANGUAGE: {reply_lang if reply_lang == 'auto' else L.name(reply_lang) + ' (' + reply_lang + ')'}\n"
            f"---- CONTENT ----\n{content}"
        )
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *self.history[-6:],
                    {"role": "user", "content": user_msg}]

        raw = await _complete(messages)
        try:
            result = _parse_json(raw)
        except Exception:
            result = {"kind": "answer", "summary": raw.strip() or "Sorry, I could not analyse that. Please try again.",
                      "verdict": "NOT_ENOUGH_INFO", "risk_score": 0}

        # Decide analysis vs follow-up answer deterministically where we can.
        is_followup = (self.last is not None and source.startswith("text") and len(content) < 400
                       and bool(_FOLLOWUP.search(content)))
        if is_followup:
            result["kind"] = "answer"
        elif result.get("kind") == "answer" and (self.last is None or not source.startswith("text") or signals["risk_floor"] >= 60):
            result["kind"] = "analysis"
        result = self._normalise(result, signals, reply_lang, stt_language, content)

        # keep compact history for follow-ups
        self.history += [
            {"role": "user", "content": user_msg[:3000]},
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
            # keep the verdict consistent with the score (e.g. after the keyword floor raised it)
            derived = _verdict_for(score)
            if verdict == "NOT_ENOUGH_INFO":
                if score >= 35:
                    verdict = derived
            elif VERDICTS.index(derived) > VERDICTS.index(verdict):
                verdict = derived
            r["verdict"] = verdict
        else:
            r["verdict"] = (self.last or {}).get("verdict", "NOT_ENOUGH_INFO")
            score = (self.last or {}).get("risk_score", 0)
        r["risk_score"] = max(0, min(100, score))
        r["keyword_signals"] = signals["hits"]
        return r
