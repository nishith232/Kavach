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
from collections import OrderedDict, defaultdict, deque

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import assistant, config, gnani, languages
from .analyzer import Session
from .scam_kb import export_rules, scan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kavach")

app = FastAPI(title="Kavach - multilingual scam detector")
app.mount("/static", StaticFiles(directory="static"), name="static")

SESSIONS: "OrderedDict[str, Session]" = OrderedDict()
_HITS: dict[str, deque] = defaultdict(deque)
PAID = {"/api/message", "/api/speak", "/api/voice/command"}


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """On a public server, stop one client from spending all the Gnani / LLM credits."""
    limit = config.RATE_LIMIT_PER_HOUR
    if limit and request.method == "POST" and request.url.path in PAID:
        ip = request.client.host if request.client else "?"
        now, q = time.time(), _HITS[ip]
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= limit:
            return JSONResponse({"error": "Too many requests from this device. Please try again in a few minutes."}, 429)
        q.append(now)
    return await call_next(request)


def get_session(sid: str) -> Session:
    s = SESSIONS.pop(sid, None) or Session()
    SESSIONS[sid] = s                      # most recently used last
    while len(SESSIONS) > config.MAX_SESSIONS:
        SESSIONS.popitem(last=False)
    return s
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
    session = get_session(sid)
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


@app.post("/api/speak")
async def speak(text: str = Form(...), language: str = Form("auto")):
    """Text -> WAV with Gnani Timbre. The phone app calls this only for real scam alerts."""
    try:
        wav = await gnani.synthesize(text[:1500], language)
        return Response(content=wav, media_type="audio/wav")
    except Exception as e:
        log.exception("speak failed")
        return JSONResponse({"error": f"{type(e).__name__}: {str(e)[:200]}"}, 502)


@app.post("/api/voice/command")
async def voice_command(
    audio: UploadFile | None = File(None),
    text: str | None = Form(None),
    records: str = Form("[]"),
    now_ms: int | None = Form(None),
    focus_id: str | None = Form(None),
    reply_language: str = Form("auto"),
    output: str = Form("both"),
):
    """Voice assistant over the phone's own scanned messages.

    audio (spoken command, Gnani Prisma) or text (typed / quick command) -> intent -> action on `records`
    (the phone's message history, JSON list) -> reply in the user's language -> Gnani Timbre voice.
    """
    timings, stt = {}, None
    try:
        if audio is not None and audio.filename:
            data = await audio.read()
            if len(data) > MAX_UPLOAD_BYTES:
                return JSONResponse({"error": "Recording is too long. Please say a short command."}, 413)
            t0 = time.perf_counter()
            stt = await gnani.transcribe(data, audio.filename)
            timings["stt_ms"] = _ms(t0)
        command = (stt["transcript"] if stt else "") or (text or "").strip()
        if not command:
            return JSONResponse({"error": "I didn't catch that. Please try again.", "transcript": ""}, 400)

        lang = assistant.reply_language(stt["language"] if stt else None, command, reply_language)
        t0 = time.perf_counter()
        intent = await assistant.classify_intent(command)
        recs = assistant.parse_records(records)
        now = now_ms or int(time.time() * 1000)
        result = assistant.run_intent(intent, recs, now, focus_id)
        reply = await assistant.translate(result["reply"], lang)
        if lang != "en-IN" and reply == result["reply"]:
            lang = "en-IN"                       # translation unavailable: speak the English reply in English
        timings["assistant_ms"] = _ms(t0)

        audio_b64, tts_error = None, None
        if output in ("voice", "both"):
            t0 = time.perf_counter()
            try:
                audio_b64 = base64.b64encode(await gnani.synthesize(reply, lang)).decode()
            except Exception as e:  # the text answer is still useful without voice
                log.exception("assistant tts failed")
                tts_error = f"{type(e).__name__}: {str(e)[:120]}"
            timings["tts_ms"] = _ms(t0)

        log.info("assistant intent=%s lang=%s records=%d matched=%d timings=%s",
                 intent, lang, len(recs), len(result["record_ids"]), timings)
        return {
            "transcript": command, "heard_by": "gnani-prisma" if stt else "text",
            "stt_language": stt["language"] if stt else None, "language": lang, "language_name": languages.name(lang),
            "intent": intent, "reply": reply, "reply_en": result["reply"], "record_ids": result["record_ids"],
            "facts": result["facts"], "audio_b64": audio_b64, "tts_error": tts_error, "timings": timings,
        }
    except Exception as e:
        log.exception("voice command failed")
        return JSONResponse({"error": f"{type(e).__name__}: {str(e)[:300]}"}, 502)


@app.get("/api/rules")
async def rules():
    """Keyword rules for on-device pre-filtering in the Kavach Guard Android app."""
    return export_rules()


@app.get("/health")
async def health():
    return {"ok": True, "sessions": len(SESSIONS)}
