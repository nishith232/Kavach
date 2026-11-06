"""Gnani clients: Prisma STT (REST for short clips, Batch for long recordings) and Timbre TTS.

Docs: https://docs.gnani.ai/api/STT/speech-to-text.md
      https://docs.gnani.ai/api/STTBatch/Introduction.md
      https://docs.gnani.ai/api/TTS/tts-inference.md
"""
import asyncio
import io
import json
import re
import wave

import httpx

from . import config
from .languages import script_of

_client = httpx.AsyncClient(timeout=60)
_auth = {"X-API-Key-ID": config.GNANI_API_KEY}


class GnaniError(RuntimeError):
    pass


RETRY_STATUS = {429, 500, 502, 503, 504}


async def _request(method: str, url: str, *, attempts: int = 5, **kw) -> httpx.Response:
    """HTTP call that waits and retries on rate limits (429) and temporary server errors.

    Honours the Retry-After header; otherwise backs off 2, 4, 8, 16 s.
    """
    delay = 2.0
    for i in range(attempts):
        r = await _client.request(method, url, **kw)
        if r.status_code not in RETRY_STATUS or i == attempts - 1:
            return r
        try:
            wait = float(r.headers.get("retry-after", delay))
        except ValueError:
            wait = delay
        await asyncio.sleep(min(wait, 30))
        delay *= 2
    return r


class RateLimited(GnaniError):
    pass


def _check(r: httpx.Response, what: str):
    if r.status_code == 429:
        raise RateLimited(f"{what} 429: Gnani rate limit reached. Please wait a minute and try again.")
    if r.status_code >= 300:
        raise GnaniError(f"{what} {r.status_code}: {r.text[:300]}")


def wav_seconds(audio: bytes) -> float | None:
    """Duration of a WAV file, or None if it isn't a readable WAV."""
    try:
        with wave.open(io.BytesIO(audio)) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return None


# ---------------------------------------------------------------- speech -> text

async def transcribe_rest(audio: bytes, filename: str) -> dict:
    """Clips up to 30 s. Fast (~300 ms)."""
    data = {"model": config.STT_MODEL, "language_code": config.STT_LANGUAGE}
    if config.STT_MODEL == "prisma-v3.0":
        data["keyterms"] = json.dumps(config.KEYTERMS)
    r = await _request("POST", f"{config.GNANI_BASE}/stt/v3", headers=_auth, data=data,
                           files={"audio_file": (filename, audio)})
    _check(r, "STT")
    body = r.json()
    if body.get("success") is False:
        raise GnaniError(f"STT failed: {body.get('error')}")
    return {
        "transcript": (body.get("transcript") or "").strip(),
        "language": body.get("detected_language_code") or "auto",
        "segments": [],
        "engine": "rest",
    }


def _find_urls(obj) -> list[str]:
    """Collect every transcript_url in a nested JSON response."""
    if isinstance(obj, dict):
        out = [obj["transcript_url"]] if isinstance(obj.get("transcript_url"), str) else []
        for v in obj.values():
            out += _find_urls(v)
        return out
    if isinstance(obj, list):
        return [u for item in obj for u in _find_urls(item)]
    return []


async def transcribe_batch(audio: bytes, filename: str, speakers: int = 2) -> dict:
    """Long recordings (up to 4 h, 10 MB direct upload). Separates speakers and tags emotion per segment."""
    cfg = {
        "model": config.STT_MODEL,
        "language_code": config.STT_LANGUAGE,
        "with_diarization": True,
        "num_speakers": speakers,
        "with_denoise": True,          # phone recordings are noisy
    }
    if config.STT_MODEL == "prisma-v3.0":
        cfg["keyterms"] = config.KEYTERMS
    r = await _request(
        "POST", f"{config.GNANI_BASE}/stt/v3/batch/jobs", headers=_auth,
        files=[("config", (None, json.dumps(cfg), "application/json")),
               ("files", (filename, audio))],
    )
    _check(r, "Batch create")
    job_id = r.json()["job_id"]

    await asyncio.sleep(1)  # give the new job a moment before starting it
    r = await _request("POST", f"{config.GNANI_BASE}/stt/v3/batch/jobs/{job_id}/start", headers=_auth, attempts=6)
    _check(r, "Batch start")

    waited, status = 0, "STARTING"
    while waited < config.BATCH_TIMEOUT_SECONDS:
        await asyncio.sleep(config.BATCH_POLL_SECONDS)
        waited += config.BATCH_POLL_SECONDS
        r = await _request("GET", f"{config.GNANI_BASE}/stt/v3/batch/jobs/{job_id}", headers=_auth)
        _check(r, "Batch status")
        status = r.json().get("status", "")
        if status in ("COMPLETED", "PARTIAL_FAILURE"):
            break
        if status in ("FAILED", "START_FAILED", "CANCELLED"):
            raise GnaniError(f"Batch job {status}: {r.text[:300]}")
    else:
        raise GnaniError(f"Batch job timed out after {waited}s (last status {status})")

    r = await _request("GET", f"{config.GNANI_BASE}/stt/v3/batch/jobs/{job_id}/files", headers=_auth)
    _check(r, "Batch files")
    urls = _find_urls(r.json())
    if not urls:
        raise GnaniError("Batch job finished but returned no transcript_url")
    r = await _request("GET", urls[0], follow_redirects=True)
    _check(r, "Transcript download")
    doc = r.json()

    segments = [
        {
            "speaker": str(s.get("speaker_id", "?")),
            "start": s.get("start_time"),
            "text": (s.get("text") or "").strip(),
            "emotion": s.get("emotion"),
            "language": s.get("language_detected"),
        }
        for s in doc.get("segments", []) if (s.get("text") or "").strip()
    ]
    if segments:
        transcript = "\n".join(f"Speaker {s['speaker']}: {s['text']}" for s in segments)
    else:
        transcript = (doc.get("full_transcript") or "").strip()
    return {
        "transcript": transcript,
        "language": doc.get("language_code") or "auto",
        "segments": segments,
        "engine": "batch",
    }


def split_wav(audio: bytes, seconds: int) -> list[bytes]:
    """Cut a WAV into pieces of at most `seconds` each."""
    with wave.open(io.BytesIO(audio)) as r:
        params, per = r.getparams(), r.getframerate() * seconds
        pieces = []
        while True:
            frames = r.readframes(per)
            if not frames:
                break
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setparams(params)
                w.writeframes(frames)
            pieces.append(buf.getvalue())
    return pieces


async def transcribe_chunked(audio: bytes) -> dict:
    """Long WAV without batch: transcribe <=28 s pieces with REST (no speaker labels)."""
    parts = []
    for i, piece in enumerate(split_wav(audio, config.REST_MAX_SECONDS)):
        if wav_seconds(piece) and wav_seconds(piece) < 0.3:
            continue
        parts.append(await transcribe_rest(piece, f"part{i}.wav"))
    langs = [p["language"] for p in parts if p["language"] != "auto"]
    return {
        "transcript": " ".join(p["transcript"] for p in parts if p["transcript"]),
        "language": max(set(langs), key=langs.count) if langs else "auto",
        "segments": [],
        "engine": "rest-chunked",
    }


async def transcribe(audio: bytes, filename: str) -> dict:
    """Short WAV -> REST. Long audio -> batch (speakers + emotion); if batch is rate-limited
    or unavailable and the audio is WAV, fall back to chunked REST."""
    secs = wav_seconds(audio)
    if secs is not None and secs <= config.REST_MAX_SECONDS:
        return await transcribe_rest(audio, filename)
    try:
        return await transcribe_batch(audio, filename)
    except GnaniError:
        if secs is None:
            raise  # mp3/ogg/m4a etc. can't be split without decoding
        return await transcribe_chunked(audio)


# ---------------------------------------------------------------- text -> speech

TTS_LANGS = {"en-IN", "hi-IN", "hi-en", "te-IN", "kn-IN", "ta-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN"}


def tts_language_for(language: str | None, text: str) -> str:
    if language in TTS_LANGS:
        return language
    guess = script_of(text)
    return guess if guess in TTS_LANGS else "auto"


async def _tts_once(text: str, language: str, sample_rate: int, voice: str | None) -> bytes:
    r = await _request(
        "POST", f"{config.GNANI_BASE}/api/v1/tts/inference",
        headers={**_auth, "Content-Type": "application/json"},
        json={
            "text": text, "model": config.TTS_MODEL, "voice": voice or config.TTS_VOICE,
            "language": language, "speed": 0.95,
            "audio_config": {"container": "wav", "sample_rate": sample_rate},
        },
    )
    _check(r, "TTS")
    return r.content


def _chunks(text: str, limit: int = 350) -> list[str]:
    """Split on sentence ends (incl. Indic danda) so each TTS request stays short."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?।॥])\s+", text) if p.strip()]
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) + 1 > limit:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        out.append(cur)
    return out or [text]


def join_wavs(wavs: list[bytes]) -> bytes:
    if len(wavs) == 1:
        return wavs[0]
    out = io.BytesIO()
    params = None
    with wave.open(out, "wb") as w:
        for b in wavs:
            with wave.open(io.BytesIO(b)) as r:
                if params is None:
                    params = r.getparams()
                    w.setparams(params)
                w.writeframes(r.readframes(r.getnframes()))
    return out.getvalue()


async def synthesize(text: str, language: str, voice: str | None = None, sample_rate: int = 24000) -> bytes:
    """Any length of text -> one WAV. Long text is spoken sentence-group by sentence-group."""
    lang = tts_language_for(language, text)
    pieces = await asyncio.gather(*[_tts_once(c, lang, sample_rate, voice) for c in _chunks(text)])
    return join_wavs(list(pieces))
