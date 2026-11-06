"""Checks every external piece once: Gnani TTS, Gnani REST STT, Gnani batch STT, and the LLM.

Run from the project root:  python -m scripts.smoke_test
"""
import asyncio
import time

from app import config, gnani
from app.analyzer import Session
from app.scam_kb import scan

LINES = "नमस्ते, मैं सीबीआई से बोल रहा हूँ। आपके आधार पर मनी लॉन्ड्रिंग का केस है। अभी पैसे ट्रांसफर कीजिए और किसी को मत बताइए।"


async def step(name, coro):
    t = time.perf_counter()
    out = await coro
    print(f"OK  {name:<14} {(time.perf_counter() - t) * 1000:6.0f} ms")
    return out


async def main():
    assert config.GNANI_API_KEY, "Set GNANI_API_KEY in .env"
    assert config.LLM_API_KEY, "Set LLM_API_KEY in .env"

    wav = await step("TTS", gnani.synthesize(LINES, "hi-IN", sample_rate=16000))
    rest = await step("STT (REST)", gnani.transcribe_rest(wav, "t.wav"))
    print("    ", rest["language"], "|", rest["transcript"])

    try:
        batch = await step("STT (batch)", gnani.transcribe_batch(wav, "t.wav"))
        print("    ", batch["language"], "|", batch["transcript"][:120])
    except gnani.GnaniError as e:
        print(f"WARN STT (batch)   {e}")
        print("     Long recordings will use the chunked fallback (WAV) until batch works.")
        long_wav = gnani.join_wavs([wav, wav, wav])  # ~3x length, > 28 s
        chunked = await step("STT (chunked)", gnani.transcribe_chunked(long_wav))
        print("    ", chunked["language"], "|", chunked["transcript"][:120])

    signals = scan(rest["transcript"])
    result = await step("LLM analysis", Session().respond(
        rest["transcript"], source="voice message", stt_language=rest["language"],
        reply_language="auto", signals=signals))
    print("    ", result["verdict"], result["risk_score"], "|", result["summary"])


if __name__ == "__main__":
    asyncio.run(main())
