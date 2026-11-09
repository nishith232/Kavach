"""Voice assistant: intent recognition, actions on real records, and the HTTP endpoint (Gnani + LLM mocked)."""
import base64
import json

import pytest
from fastapi.testclient import TestClient

from app import assistant, gnani, main

NOW = 1_800_000_000_000
MIN = 60_000
RECORDS = [
    {"id": "a", "time": NOW - 5 * MIN, "app": "Messages", "sender": "VM-ELECTR", "verdict": "SCAM", "risk": 90,
     "scam_type": "Electricity / bill disconnection", "summary": "Fake power cut threat.",
     "red_flags": ["disconnected tonight"], "actions": ["Do not call the number."]},
    {"id": "b", "time": NOW - 20 * MIN, "app": "WhatsApp", "sender": "Mom", "verdict": "LIKELY_SAFE", "risk": 5},
    {"id": "c", "time": NOW - 50 * MIN, "app": "Messages", "sender": "", "verdict": "CLEAN", "risk": 0},
    {"id": "d", "time": NOW - 3 * 60 * MIN, "app": "Gmail", "sender": "", "verdict": "SUSPICIOUS", "risk": 45,
     "scam_type": "Lottery / prize / refund", "summary": "Unexpected refund link."},
]


@pytest.mark.parametrize("text,intent", [
    ("Check my messages from the last hour", "last_hour"),
    ("Show my suspicious messages", "suspicious"),
    ("Show my genuine messages", "genuine"),
    ("Read my latest security alerts", "latest_alerts"),
    ("Give me a summary of my scanned messages", "summary"),
    ("Explain why this message is suspicious", "explain"),
    ("pichle ghante ke messages check karo", "last_hour"),
    ("मेरे संदिग्ध मैसेज दिखाओ", "suspicious"),
    ("నా అలర్ట్స్ చదువు", "latest_alerts"),
    ("I already paid them", None),
])
def test_intents(text, intent):
    assert assistant.match_intent(text) == intent


def recs():
    return assistant.clean_records(RECORDS)


def test_last_hour_counts_only_real_records():
    r = assistant.run_intent("last_hour", recs(), NOW)
    assert "3 messages" in r["reply"] and "1 fraudulent" in r["reply"] and "2 genuine" in r["reply"]
    assert r["record_ids"] == ["a"] and r["facts"] == {"total": 3, "fraud": 1, "suspicious": 0, "genuine": 2}


def test_suspicious_lists_threats_newest_first():
    r = assistant.run_intent("suspicious", recs(), NOW)
    assert r["record_ids"] == ["a", "d"] and "2 suspicious or fraudulent messages" in r["reply"]


def test_genuine_and_empty_history():
    assert assistant.run_intent("genuine", recs(), NOW)["record_ids"] == ["b", "c"]
    empty = assistant.run_intent("summary", [], NOW)
    assert empty["reply"] == "I haven't scanned any messages yet." and empty["record_ids"] == []


def test_explain_uses_focus_record_and_its_evidence():
    r = assistant.run_intent("explain", recs(), NOW, focus_id="d")
    assert r["record_ids"] == ["d"] and "Unexpected refund link." in r["reply"]
    r = assistant.run_intent("explain", recs(), NOW)          # no focus: latest threat
    assert r["record_ids"] == ["a"] and '"disconnected tonight"' in r["reply"]


def test_unknown_command_is_handled():
    r = assistant.run_intent("unknown", recs(), NOW)
    assert "can't do that" in r["reply"] and r["record_ids"] == []


def test_reply_language():
    assert assistant.reply_language("te-IN", "x", "auto") == "te-IN"
    assert assistant.reply_language(None, "mere alerts dikhao", "auto") == "hi-en"
    assert assistant.reply_language("hi-IN", "x", "ta-IN") == "ta-IN"


def test_endpoint_with_audio(monkeypatch):
    async def fake_stt(data, filename):
        return {"transcript": "Show my suspicious messages", "language": "en-IN", "segments": [], "engine": "rest"}

    async def fake_tts(text, language, **kw):
        assert language == "en-IN" and "2 suspicious" in text
        return b"RIFFfake"
    monkeypatch.setattr(gnani, "transcribe", fake_stt)
    monkeypatch.setattr(gnani, "synthesize", fake_tts)
    client = TestClient(main.app)
    res = client.post("/api/voice/command", files={"audio": ("cmd.wav", b"RIFF....WAVE", "audio/wav")},
                      data={"records": json.dumps(RECORDS), "now_ms": str(NOW)})
    body = res.json()
    assert res.status_code == 200, body
    assert body["intent"] == "suspicious" and body["record_ids"] == ["a", "d"] and body["heard_by"] == "gnani-prisma"
    assert base64.b64decode(body["audio_b64"]) == b"RIFFfake"


def test_endpoint_translates_and_survives_tts_failure(monkeypatch):
    async def fake_translate(text, lang):
        return "अनुवाद: " + text

    async def broken_tts(text, language, **kw):
        raise gnani.GnaniError("TTS 429")
    monkeypatch.setattr(assistant, "translate", fake_translate)
    monkeypatch.setattr(gnani, "synthesize", broken_tts)
    client = TestClient(main.app)
    res = client.post("/api/voice/command", data={"text": "मेरे संदिग्ध मैसेज दिखाओ", "records": json.dumps(RECORDS),
                                                   "now_ms": str(NOW)})
    body = res.json()
    assert res.status_code == 200 and body["language"] == "hi-IN" and body["reply"].startswith("अनुवाद")
    assert body["audio_b64"] is None and "429" in body["tts_error"]


def test_endpoint_rejects_empty_command():
    res = TestClient(main.app).post("/api/voice/command", data={"records": "[]"})
    assert res.status_code == 400


def test_rate_limit_blocks_after_limit(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "RATE_LIMIT_PER_HOUR", 2)
    main._HITS.clear()
    client = TestClient(main.app)
    codes = [client.post("/api/voice/command", data={"text": "summary", "records": "[]", "output": "text"}).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]
    assert client.get("/health").status_code == 200      # free endpoints never limited
    main._HITS.clear()


def test_sessions_are_capped(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "MAX_SESSIONS", 3)
    main.SESSIONS.clear()
    for i in range(5):
        main.get_session(f"s{i}")
    assert list(main.SESSIONS) == ["s2", "s3", "s4"]
    main.SESSIONS.clear()


def test_api_keys_never_shown_in_errors(monkeypatch):
    from app import config
    secret = "vach_SECRET_KEY_123456"
    monkeypatch.setattr(config, "GNANI_API_KEY", secret)

    async def boom(*a, **k):
        raise RuntimeError(f"Illegal header value b'{secret}\\n'")
    monkeypatch.setattr(gnani, "synthesize", boom)
    body = TestClient(main.app).post("/api/speak", data={"text": "hi"}).json()
    assert secret not in body["error"] and "[hidden]" in body["error"]
