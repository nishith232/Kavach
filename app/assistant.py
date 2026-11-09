"""Kavach voice assistant: a spoken command about the user's OWN scanned messages -> action -> spoken reply.

The scanned messages live on the phone, so the app sends its records with each command.
Every count, message and explanation in the reply is computed from those records here;
the LLM is only used to (a) recognise the command when keywords don't, and (b) translate the
finished reply into the user's language. It never decides numbers.
"""
import json
import logging
import re

from . import config, languages as L

log = logging.getLogger("kavach")

INTENTS = ("last_hour", "suspicious", "fraud", "genuine", "latest_alerts", "summary", "explain", "unknown")
THREAT = {"SCAM", "LIKELY_SCAM", "SUSPICIOUS"}
FRAUD = {"SCAM", "LIKELY_SCAM"}
GENUINE = {"LIKELY_SAFE", "CLEAN"}
VERDICT_WORDS = {"SCAM": "a scam", "LIKELY_SCAM": "likely a scam", "SUSPICIOUS": "suspicious",
                 "LIKELY_SAFE": "genuine", "CLEAN": "clean", "NOT_ENOUGH_INFO": "unclear"}

# First match wins, so "explain why this is suspicious" is an explanation, not a list.
_PATTERNS = [
    ("explain", r"\bexplain\b|\bwhy\b|\bkyu+n\b|\bkyon\b|क्यों|समझा|ఎందుకు|వివరించ|ஏன்|விளக்க|ಏಕೆ|ವಿವರಿಸ"),
    ("last_hour", r"(last|past|this|previous) hour|\bghante\b|घंटे|గంట|மணி நேர|ಗಂಟೆ"),
    ("summary", r"summary|summari[sz]e|overview|how many|\bkitne\b|कितने|सारांश|సారాంశం|ఎన్ని|சுருக்கம்|எத்தனை|ಸಾರಾಂಶ|ಎಷ್ಟು"),
    ("latest_alerts", r"\balerts?\b|\blatest\b|\brecent\b|\bread\b|\bwarnings?\b|अलर्ट|चेतावनी|पढ़|అలర్ట్|హెచ్చరిక|చదువు|எச்சரிக்கை|படி|ಎಚ್ಚರಿಕೆ|ಓದು"),
    ("fraud", r"\bfraud|\bscams?\b|फ्रॉड|धोखा|स्कैम|మోసం|స్కామ్|மோசடி|ವಂಚನೆ"),
    ("suspicious", r"suspicious|\brisky\b|danger|sandigdh|संदिग्ध|खतरना|అనుమాన|சந்தேக|ಅನುಮಾನ|ಶಂಕಾಸ್ಪದ"),
    ("genuine", r"genuine|\bsafe\b|\breal\b|\blegit|\basli\b|असली|सुरक्षित|నిజమైన|సురక్షిత|உண்மையான|பாதுகாப்பான|ನಿಜವಾದ|ಸುರಕ್ಷಿತ"),
]
_COMPILED = [(i, re.compile(p, re.I)) for i, p in _PATTERNS]
_HINGLISH = re.compile(r"\b(mere|mera|meri|kya|dikhao|batao|sunao|hai|hain|kitne|kaun|wale)\b", re.I)


def match_intent(text: str) -> str | None:
    for intent, rx in _COMPILED:
        if rx.search(text or ""):
            return intent
    return None


async def classify_intent(text: str) -> str:
    """Keywords first (instant, any of our languages); the LLM only for phrasings they miss."""
    intent = match_intent(text)
    if intent or not config.LLM_API_KEY or not (text or "").strip():
        return intent or "unknown"
    from .analyzer import _complete, _parse_json
    prompt = (
        "Classify a voice command to a scam-protection app about the user's scanned messages. "
        f"Reply with JSON {{\"intent\": one of {list(INTENTS)}}}.\n"
        "last_hour=check/summarise messages from the last hour; suspicious=list risky messages; fraud=list scam messages; "
        "genuine=list safe messages; latest_alerts=read the latest alerts; summary=overall summary or counts; "
        "explain=why a message is suspicious; unknown=anything else.")
    try:
        raw, _ = await _complete([{"role": "system", "content": prompt}, {"role": "user", "content": text[:500]}])
        intent = str(_parse_json(raw).get("intent", "unknown"))
    except Exception:
        log.exception("intent classification failed")
        return "unknown"
    return intent if intent in INTENTS else "unknown"


def reply_language(stt_language: str | None, text: str, requested: str | None) -> str:
    """User's setting if set; else the language they spoke (Prisma's guess, then the script)."""
    lang = L.normalise(requested)
    if lang:
        return lang
    lang = L.normalise(stt_language) or L.script_of(text or "") or "en-IN"
    if lang == "en-IN" and _HINGLISH.search(text or ""):
        return "hi-en"
    return lang


# ------------------------------------------------------------------ records

def clean_records(raw) -> list[dict]:
    """Validate the records the phone sent; newest first."""
    out = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        try:
            t = int(r.get("time") or 0)
        except (TypeError, ValueError):
            continue
        out.append({
            "id": str(r["id"]), "time": t, "app": str(r.get("app") or "a message"),
            "sender": str(r.get("sender") or ""), "verdict": str(r.get("verdict") or "").upper(),
            "risk": int(r.get("risk") or 0) if str(r.get("risk") or "0").lstrip("-").isdigit() else 0,
            "scam_type": str(r.get("scam_type") or ""), "summary": str(r.get("summary") or "")[:400],
            "snippet": str(r.get("snippet") or "")[:200],
            "red_flags": [str(x)[:120] for x in (r.get("red_flags") or [])][:3],
            "actions": [str(x)[:160] for x in (r.get("actions") or [])][:2],
        })
    return sorted(out, key=lambda r: r["time"], reverse=True)


def _ago(ms: int, now_ms: int) -> str:
    mins = max(0, (now_ms - ms) // 60000)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} minute{'s' * (mins != 1)} ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours} hour{'s' * (hours != 1)} ago"
    days = hours // 24
    return f"{days} day{'s' * (days != 1)} ago"


def _who(r: dict) -> str:
    return f"{r['app']}" + (f" ({r['sender']})" if r["sender"] and r["sender"] not in r["app"] else "")


def _kind(r: dict) -> str:
    t = r["scam_type"] if r["scam_type"] and r["scam_type"].lower() != "none" else ""
    return VERDICT_WORDS.get(r["verdict"], "unchecked") + (f", {t}" if t else "")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' * (n != 1)}"


def _counts(rs: list[dict]) -> dict:
    return {"total": len(rs), "fraud": sum(r["verdict"] in FRAUD for r in rs),
            "suspicious": sum(r["verdict"] == "SUSPICIOUS" for r in rs),
            "genuine": sum(r["verdict"] in GENUINE for r in rs)}


def run_intent(intent: str, records: list[dict], now_ms: int, focus_id: str | None = None) -> dict:
    """-> {"reply": English reply built only from the records, "record_ids": [...], "facts": {...}}"""
    if intent == "last_hour":
        rs = [r for r in records if now_ms - r["time"] <= 3600_000]
        c = _counts(rs)
        if not rs:
            return {"reply": "I haven't scanned any messages in the last hour.", "record_ids": [], "facts": c}
        reply = (f"In the last hour I checked {_plural(c['total'], 'message')}: {c['fraud']} fraudulent, "
                 f"{c['suspicious']} suspicious and {c['genuine']} genuine.")
        threats = [r for r in rs if r["verdict"] in THREAT]
        if threats:
            top = max(threats, key=lambda r: r["risk"])
            reply += f" The most serious is from {_who(top)}, {_ago(top['time'], now_ms)}: {_kind(top)}."
        else:
            reply += " Nothing risky."
        return {"reply": reply, "record_ids": [r["id"] for r in (threats or rs)][:10], "facts": c}

    if intent in ("suspicious", "fraud", "genuine"):
        wanted = {"suspicious": THREAT, "fraud": FRAUD, "genuine": GENUINE}[intent]
        label = {"suspicious": "suspicious or fraudulent", "fraud": "fraudulent", "genuine": "genuine"}[intent]
        rs = [r for r in records if r["verdict"] in wanted]
        if not rs:
            return {"reply": f"You have no {label} messages in your history.", "record_ids": [], "facts": {"count": 0}}
        items = "; ".join(f"from {_who(r)}, {_ago(r['time'], now_ms)}, {_kind(r)}" for r in rs[:3])
        reply = f"You have {_plural(len(rs), label + ' message')}. The latest: {items}."
        return {"reply": reply, "record_ids": [r["id"] for r in rs][:20], "facts": {"count": len(rs)}}

    if intent == "latest_alerts":
        rs = [r for r in records if r["verdict"] in THREAT][:3]
        if not rs:
            return {"reply": "You have no security alerts. No risky messages have been found.", "record_ids": [], "facts": {"count": 0}}
        parts = [f"{i}. From {_who(r)}, {_ago(r['time'], now_ms)}: {_kind(r)}. {r['summary']}" for i, r in enumerate(rs, 1)]
        reply = f"Here are your latest {_plural(len(rs), 'alert')}. " + " ".join(parts)
        return {"reply": reply, "record_ids": [r["id"] for r in rs], "facts": {"count": len(rs)}}

    if intent == "summary":
        c = _counts(records)
        if not records:
            return {"reply": "I haven't scanned any messages yet.", "record_ids": [], "facts": c}
        today = [r for r in records if now_ms - r["time"] <= 86400_000]
        reply = (f"So far I have {_plural(c['total'], 'scanned message')} in your history: {c['fraud']} fraudulent, "
                 f"{c['suspicious']} suspicious and {c['genuine']} genuine. {len(today)} of them arrived in the last 24 hours.")
        types = [r["scam_type"] for r in records if r["verdict"] in THREAT and r["scam_type"] and r["scam_type"].lower() != "none"]
        if types:
            common = max(set(types), key=types.count)
            reply += f" The most common threat is {common}."
        threats = [r for r in records if r["verdict"] in THREAT]
        if threats:
            reply += f" The latest alert was from {_who(threats[0])}, {_ago(threats[0]['time'], now_ms)}."
        return {"reply": reply, "record_ids": [r["id"] for r in threats][:10], "facts": c}

    if intent == "explain":
        r = next((x for x in records if x["id"] == focus_id), None) if focus_id else None
        r = r or next((x for x in records if x["verdict"] in THREAT), None)
        if not r:
            return {"reply": "There is no suspicious message to explain yet.", "record_ids": [], "facts": {}}
        reply = f"The message from {_who(r)}, {_ago(r['time'], now_ms)}, was marked {_kind(r)}, risk {r['risk']} out of 100."
        if r["summary"]:
            reply += f" {r['summary']}"
        if r["red_flags"]:
            reply += " Warning signs: " + "; ".join(f"\"{q}\"" for q in r["red_flags"]) + "."
        if r["actions"]:
            reply += " What to do: " + " ".join(r["actions"])
        return {"reply": reply, "record_ids": [r["id"]], "facts": {"risk": r["risk"]}}

    return {"reply": ("Sorry, I can't do that yet. You can say: check my messages from the last hour, "
                      "show my suspicious messages, show my genuine messages, read my latest alerts, "
                      "give me a summary, or explain why a message is suspicious."),
            "record_ids": [], "facts": {}}


async def translate(text: str, lang: str) -> str:
    """Faithful translation of a finished reply. Falls back to the English text on any failure."""
    if lang == "en-IN" or not config.LLM_API_KEY:
        return text
    from .analyzer import _complete, _parse_json
    script = "Latin script (Hinglish)" if lang == "hi-en" else "its native script"
    prompt = (f"Translate the assistant reply into {L.name(lang)} ({lang}) in {script}, to be read aloud. "
              "Keep every number, app name and quoted text exactly. Do not add, remove or change any information. "
              'Reply with JSON {"text": "<translation>"}.')
    try:
        raw, _ = await _complete([{"role": "system", "content": prompt}, {"role": "user", "content": text}])
        out = str(_parse_json(raw).get("text") or "").strip()
        return out or text
    except Exception:
        log.exception("translation failed")
        return text


def parse_records(records_json: str | None) -> list[dict]:
    try:
        return clean_records(json.loads(records_json or "[]"))
    except (json.JSONDecodeError, TypeError):
        return []
