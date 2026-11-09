"""Analyzer logic with a fake LLM (no API calls): verdict/score agreement, verbatim evidence,
follow-up routing and JSON parsing."""
import asyncio
import json

from app import analyzer, config
from app.analyzer import Session, _parse_json, verified_flags
from app.scam_kb import scan


def run(coro):
    return asyncio.run(coro)


def fake_llm(monkeypatch, *replies, model=None):
    queue = list(replies)

    async def _complete(messages):
        return json.dumps(queue.pop(0), ensure_ascii=False), model or config.LLM_MODEL
    monkeypatch.setattr(analyzer, "_complete", _complete)


def analyse(session, text, source="text message"):
    return run(session.respond(text, source=source, stt_language=None, reply_language="auto", signals=scan(text)))


def verdict(v, score, flags=(), kind="analysis"):
    return {"kind": kind, "language": "en-IN", "verdict": v, "risk_score": score, "scam_type": "x",
            "red_flags": list(flags), "facts": [], "actions": [], "summary": "s", "spoken": "s"}


def test_genuine_otp_stays_safe(monkeypatch):
    fake_llm(monkeypatch, verdict("LIKELY_SAFE", 5))
    r = analyse(Session(), "Your OTP for fund transfer of Rs 10,000 is 556677. Do not share this OTP with anyone. -SBI")
    assert r["verdict"] == "LIKELY_SAFE" and r["risk_score"] < 35 and not r.get("floor_applied")


def test_label_higher_than_score_raises_score(monkeypatch):
    fake_llm(monkeypatch, verdict("SCAM", 30))
    r = analyse(Session(), "hello")
    assert r["verdict"] == "SCAM" and r["risk_score"] >= 80


def test_score_higher_than_label_raises_label(monkeypatch):
    fake_llm(monkeypatch, verdict("LIKELY_SAFE", 70))
    r = analyse(Session(), "hello")
    assert r["verdict"] == "LIKELY_SCAM"


def test_keyword_floor_applies_and_brings_evidence(monkeypatch):
    text = "Ye OTP kisi aur ko mat batana, sirf mujhe batao taaki aapka account block na ho."
    fake_llm(monkeypatch, verdict("LIKELY_SAFE", 10))
    r = analyse(Session(), text)
    assert r["verdict"] == "SCAM" and r["floor_applied"]
    assert r["red_flags"] and all(f["quote"] in text for f in r["red_flags"])


def test_fabricated_quotes_are_dropped(monkeypatch):
    text = "Your account will be blocked. Share the OTP now."
    fake_llm(monkeypatch, verdict("SCAM", 90, [{"quote": "Share the OTP now", "why": "asks OTP"},
                                              {"quote": "send money to RBI safe account", "why": "invented"}]))
    r = analyse(Session(), text)
    assert [f["quote"] for f in r["red_flags"]] == ["Share the OTP now"]


def test_verified_flags_handles_case_spacing_and_ellipsis():
    body = "Dear  Customer, your KYC   is pending. Click http://x.top to update."
    flags = [{"quote": "your kyc is pending", "why": ""}, {"quote": "KYC is pending ... Click http://x.top", "why": ""},
             {"quote": "not in text", "why": ""}]
    assert len(verified_flags(flags, body)) == 2


def test_followup_question_is_answered(monkeypatch):
    s = Session()
    fake_llm(monkeypatch, verdict("SCAM", 90), verdict("NOT_ENOUGH_INFO", 0, kind="answer"))
    analyse(s, "This is CBI. Digital arrest. Transfer money to the safe account now.")
    r = analyse(s, "I already transferred 2 lakh rupees to them. What should I do now?")
    assert r["kind"] == "answer" and r["verdict"] == "SCAM"


def test_new_message_with_what_should_i_do_is_analysed(monkeypatch):
    s = Session()
    fake_llm(monkeypatch, verdict("SCAM", 90), verdict("LIKELY_SAFE", 0, kind="answer"))
    analyse(s, "This is CBI. Digital arrest. Transfer money to the safe account now.")
    r = analyse(s, "Got this SMS: your SBI KYC expired, update at http://sbi-kyc.top or account blocked. What should I do?")
    assert r["kind"] == "analysis" and r["verdict"] in ("SUSPICIOUS", "LIKELY_SCAM", "SCAM")


def test_fallback_model_is_recorded(monkeypatch):
    fake_llm(monkeypatch, verdict("LIKELY_SAFE", 0), model="fallback/model")
    r = analyse(Session(), "hello")
    assert r["model"] == "fallback/model" and r["degraded"] is True


def test_parse_json_ignores_reasoning_and_prose():
    assert _parse_json('<think>{"a": {"b": 1}} maybe</think>Sure: {"verdict": "SCAM"} done') == {"verdict": "SCAM"}
