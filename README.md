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

## 📱 Kavach Guard: Android app (automatic message shield)
Kavach Guard reads every incoming notification (SMS, WhatsApp, Telegram, email) **the moment it arrives**, before you open it.
- Each message is checked **on the phone** with the same scam rules and scoring as the server. Only suspicious ones are sent to the Kavach server for an AI verdict.
- Scams trigger a **heads-up warning** with a "Call 1930" button, plus a **spoken warning** in your language (Gnani TTS).
- Includes a modern dark UI: radar shield, alert feed with risk gauge, manual "Check a message" screen, settings.
- If the server is unreachable, strong on-device matches still trigger a warning.

- **History:** every scanned message is saved on the phone (newest 200, survives restarts) with a stable id.
  Tap any Live Scan row, dashboard tile, notification or History item to open that exact message: original text,
  app, sender, time, verdict, risk, red flags, explanation and what to do. Filters: All / Genuine / Suspicious / Fraudulent.
  Messages only checked on the phone can get a full check with **Analyse with AI**.
- **Ask Kavach (voice assistant):** tap the mic in the *Ask* tab and speak (Gnani Prisma), e.g. "Check my messages from
  the last hour", "Show my suspicious messages", "Show my genuine messages", "Read my latest security alerts",
  "Give me a summary of my scanned messages", "Explain why this message is suspicious". The answer is built only from
  your real saved records, translated into the language you spoke, and read aloud with Gnani Timbre. Quick-command
  chips do the same without speaking. On a threat's detail screen, **Explain aloud** explains that exact message.

**Install:** on the phone, open
https://github.com/nishith232/Kavach/releases/download/android-latest/KavachGuard.apk
(it's rebuilt automatically by GitHub Actions on every change to `android/`).

**Live server:** https://kavach-yqti.onrender.com (web app + API, hosted on Render's free plan from `render.yaml`).
The Android app uses it by default, so no laptop is needed. The free server sleeps after 15 minutes idle; the first
request then takes about 50 seconds. To deploy your own: Render → New → Blueprint → this repo, and enter
`GNANI_API_KEY` and `LLM_API_KEY`.

**Or connect it to a server on your laptop:**
1. On the laptop: `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000` (allow it through Windows Firewall on private networks).
2. Find the laptop's Wi-Fi IPv4 address with `ipconfig` (e.g. 192.168.1.7).
3. In the app: Settings → AI server → `http://192.168.1.7:8000` → **Test connection**. The phone must be on the same Wi-Fi.

**Turn on the shield (Android 13+ sideloaded apps):** Home → *Allow notification access*. If Android shows "Restricted setting",
open App info → ⋮ → **Allow restricted settings**, then try again. On iQOO/vivo also allow background activity:
Settings → Battery → Background power consumption management → Kavach Guard → Allow.

## Demo video autopilot
Drives the live website by itself (real AI verdicts and Gnani voices), with captions and a spoken voice-over by Gnani Timbre, for screen recording:
```powershell
uv run --with playwright playwright install chromium     # once
uv run --with playwright python -m scripts.demo_autopilot --recording "C:\path\to\scam_call.m4a"
```
Start Windows recording (Win + Alt + R) when it asks, press Enter, and stop when it says the demo is finished.

## Unit tests (no API keys needed)
```powershell
uv run python -m pytest tests -q        # keyword layer, analyzer logic (fake LLM), voice assistant + endpoint (mocked Gnani)
```

## Testing (56 realistic cases)
`tests/cases.json` holds realistic, fictional cases modelled on real Indian scam scripts:
- **3 per fraud type** (33): different languages (Hindi, Telugu, Kannada, Tamil, English, Hinglish), channels
  (call recordings with speakers, SMS, WhatsApp, victims describing what happened) and difficulty
- **8 safe look-alikes**: a real OTP SMS, a debit alert, COD delivery, family money message, real power bill,
  a genuine bank callback, real police passport verification, friends discussing stocks
- **7 edge cases**: too-short message, Telugu-English code-mixing, Telugu written in Devanagari, a general question,
  a **prompt-injection** attempt, reply-language override, and a **multi-turn follow-up** ("I already paid, what now?")

```powershell
py -m scripts.run_tests --offline          # keyword layer only, instant, no API use
py -m scripts.run_tests                    # full AI verdicts -> tests/report.md
py -m scripts.run_tests --category sextortion
py -m scripts.run_tests --audio --only DA-1 UP-2   # TTS -> STT -> analysis (uses Gnani credits)
```
The report shows pass rate, **scams caught**, **false alarms on safe messages**, results per fraud type, and details for each failure.

## How the verdict is made (good for your interview)
- **Two layers.** A deterministic multilingual keyword scan sets a *risk floor*: the AI can raise the score but never rate an obvious scam as safe. The LLM then reasons over known Indian scam playbooks and verified facts, and must quote evidence verbatim.
- **Calibrated.** Explicit SAFE and NOT_ENOUGH_INFO verdicts, so real OTP messages and normal calls aren't flagged.
- **Speaker-aware.** Batch STT separates caller and victim, and its emotion tags (fear, anger) add a "pressure" signal.
- **Language end to end.** The input is analysed in its own language; the reply follows the input or the user's choice. The voice uses the verified language.

## Limits (say these honestly in the demo)
- REST STT takes up to 30 s; longer audio uses batch (up to 4 h, 10 MB direct upload), which takes longer.
- It gives guidance, not legal advice. For real losses, call **1930** immediately.
