# 🛡️ Kavach: multilingual scam detector on Gnani AI

Send a suspicious **call recording, voice note, spoken description, or text message**, in any of 11 Indian languages.
Kavach tells you whether it's a scam, **quotes the exact red-flag words**, gives the facts that disprove them, and tells you what to do.
You get the answer as **text, voice, or both**, in the same language or one you choose, and you can ask follow-up questions in any mode.

```
 INPUT (any)                    UNDERSTAND                          DECIDE                          OUTPUT (your choice)
 🎙 mic (≤28 s) ──► Prisma REST ─┐                                                                  📝 text card
 📎 recording   ──► Prisma Batch ─┼─► transcript ─► keyword scan ─► LLM (playbooks + facts) ─► verdict ─┤
    (speakers, emotion, denoise)  │   (any language)  (risk floor)     JSON, user's language        🔊 Timbre voice
 ⌨ text  ─────────────────────────┘                                                                  (or both)
```

## Why it matters
Digital-arrest fraud alone caused ₹4,057.7 crore in losses across India between 2022 and May 2026 (about 2.98 lakh complaints).
Most victims are elderly and not English-first. Kavach meets them in their language, by voice.

## Project layout
```
app/
  config.py      settings, STT keyterms (CBI, OTP, KYC, AnyDesk…)
  languages.py   11 languages: names, scripts, fallbacks
  gnani.py       Prisma REST + Batch (diarization, emotion, denoise), Timbre TTS (long text chunked + joined)
  scam_kb.py     Indian scam playbooks, verified facts, multilingual keyword scan -> risk floor
  analyzer.py    LLM -> structured verdict JSON; follow-up Q&A with session memory
  main.py        POST /api/message (audio and/or text in; text/voice/both out)
static/index.html  chat UI: record / upload / paste, output toggle, reply language
scripts/smoke_test.py   checks Gnani TTS, REST STT, batch STT and the LLM once
scripts/make_samples.py generates demo scam calls with two Gnani voices + sample SMS
```

## Run it
With [uv](https://docs.astral.sh/uv/):
```powershell
uv sync                                # creates .venv and installs everything
copy .env.example .env                 # then put your GNANI_API_KEY and LLM_API_KEY in .env
uv run python -m scripts.smoke_test    # every line should say OK
uv run python -m scripts.make_samples  # creates samples/*.wav + sample_messages.txt
uv run uvicorn app.main:app --reload --port 8000
```
(Without uv: `python -m venv .venv`, activate it, `pip install -r requirements.txt`, then the same commands without `uv run`.)
Open http://localhost:8000.

## Try these
1. 📎 Upload `samples/hindi_digital_arrest.wav`, set "Reply in Telugu" and "Both". The Hindi call is explained in Telugu, by voice.
2. Then type: *"I already sent 20,000, what now?"* to get a follow-up answer in context.
3. 📎 `samples/telugu_safe_delivery.wav` should come back as **Looks safe** (no false alarm).
4. ⌨ Paste the SMS samples from `samples/sample_messages.txt` (including a real OTP SMS, which should be safe).
5. 🎙 Speak: *"Someone called saying my SIM will be blocked by TRAI and I must press 9."*

## How the verdict is made (good for your interview)
- **Two layers.** A deterministic multilingual keyword scan sets a *risk floor*: the AI can raise the score but never rate an obvious scam as safe. The LLM then reasons over known Indian scam playbooks and verified facts, and must quote evidence verbatim.
- **Calibrated.** Explicit SAFE and NOT_ENOUGH_INFO verdicts, so real OTP messages and normal calls aren't flagged.
- **Speaker-aware.** Batch STT separates caller and victim, and its emotion tags (fear, anger) add a "pressure" signal.
- **Language end to end.** The input is analysed in its own language; the reply follows the input or the user's choice. The voice uses the verified language.

## Limits (say these honestly in the demo)
- REST STT takes up to 30 s; longer audio uses batch (up to 4 h, 10 MB direct upload), which takes longer.
- It gives guidance, not legal advice. For real losses, call **1930** immediately.
