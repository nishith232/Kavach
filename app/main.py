"""Kavach API: any input (audio or text) -> scam verdict -> any output (text, voice, or both).

POST /api/message  (multipart form)
  audio           optional file: call recording / voice note / mic recording (wav, mp3, ogg, opus, m4a, amr, webm, mp4)
  text            optional: pasted SMS / WhatsApp message / transcript / question
  output          "text" | "voice" | "both"            (default "both")
  reply_language  "auto" (same as input) | "te-IN" | "hi-IN" | ...
  session_id      keeps context for follow-up questions
"""
import base64
import logging
import time
import uuid

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import gnani, languages
from .analyzer import Session
from .scam_kb import scan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kavach")

app = FastAPI(title="Kavach - multilingual scam detector")
app.mount("/static", StaticFiles(directory="static"), name="static")

SESSIONS: dict[str, Session] = {}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # Gnani batch direct-upload limit


def _ms(t0: float) -> int:
    return round((time.perf_counter() - t0) * 1000)


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.post("/api/message")
async def message(
    audio: UploadFile | None = File(None),
    text: str | None = Form(None),
    output: str = Form("both"),
    reply_language: str = Form("auto"),
    session_id: str | None = Form(None),
):
    sid = session_id or uuid.uuid4().hex
    session = SESSIONS.setdefault(sid, Session())
    output = output if output in ("text", "voice", "both") else "both"
    timings, stt = {}, None

    try:
        # 1) INPUT -> text
        parts = []
        if audio is not None and audio.filename:
            data = await audio.read()
            if len(data) > MAX_UPLOAD_BYTES:
                return JSONResponse({"session_id": sid, "error": "Audio file is over 10 MB. Please trim it or send a shorter clip."}, 413)
            t0 = time.perf_counter()
            stt = await gnani.transcribe(data, audio.filename)
            timings["stt_ms"] = _ms(t0)
            if stt["transcript"]:
                parts.append(stt["transcript"])
        if text and text.strip():
            parts.append(text.strip())
        if not parts:
            return JSONResponse({"session_id": sid, "error": "Nothing to check. Record, upload, or paste something."}, 400)

        source = ("call recording / voice note" if stt and stt["engine"] == "batch" else "voice message") if stt else "text message"
        if stt and text and text.strip():
            source += " + text note"
        content = "\n\n".join(parts)

        # 2) ANALYSE
        signals = scan(content, stt["segments"] if stt else None)
        t0 = time.perf_counter()
        result = await session.respond(
            content, source=source, stt_language=stt["language"] if stt else languages.script_of(content),
            reply_language=reply_language, signals=signals,
        )
        timings["llm_ms"] = _ms(t0)

        # 3) OUTPUT -> voice (if wanted)
        audio_b64 = None
        if output in ("voice", "both") and result.get("spoken"):
            t0 = time.perf_counter()
            wav = await gnani.synthesize(result["spoken"], result["language"])
            timings["tts_ms"] = _ms(t0)
            audio_b64 = base64.b64encode(wav).decode()

        log.info("sid=%s src=%s in=%s out=%s verdict=%s risk=%s flags=%d timings=%s",
                 sid[:6], source, result.get("input_language"), result["language"],
                 result.get("verdict"), result.get("risk_score"), len(signals["hits"]), timings)

        return {
            "session_id": sid,
            "input": {
                "source": source,
                "transcript": stt["transcript"] if stt else None,
                "segments": stt["segments"] if stt else [],
                "stt_engine": stt["engine"] if stt else None,
                "stt_language": stt["language"] if stt else None,
                "text": text,
            },
            "result": result,
            "output": output,
            "audio_b64": audio_b64,
            "timings": timings,
        }
    except Exception as e:  # show a readable error in the UI instead of a bare 500
        log.exception("message failed")
        return JSONResponse({"session_id": sid, "error": f"{type(e).__name__}: {str(e)[:300]}"}, 502)


@app.get("/health")
async def health():
    return {"ok": True, "sessions": len(SESSIONS)}
