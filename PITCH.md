# Kavach Guard: Solution Pitch

**An AI scam shield for India that speaks the user's language, built on Gnani AI's voice models.**
Live demo: https://kavach-yqti.onrender.com · Android app: [KavachGuard.apk](https://github.com/nishith232/Kavach/releases/download/android-latest/KavachGuard.apk) · Code: https://github.com/nishith232/Kavach

## Problem
Fake "digital arrest" calls, KYC-expiry SMS, electricity-disconnection threats, prize and investment scams reach millions
of Indians every day, in Hindi, Telugu, Tamil, Hinglish and other languages. Digital-arrest fraud alone has cost Indians
thousands of crores in recent years. The people hit hardest are often elderly and not English-first: existing warnings
are in English, and a scam call leaves no text to check.

## Solution
Kavach checks any suspicious **SMS, WhatsApp message, voice note or recorded phone call** in **11 Indian languages**
(including Hinglish and code-mixed speech), decides whether it is a scam, **quotes the exact red-flag words**, gives the
facts that disprove them, and tells the user what to do, as **text or voice, in their own language**.

- **Android app (automatic shield):** reads every incoming notification, checks it on the phone, and warns the user
  before they open the message, with a spoken alert and a one-tap call to the **1930** cyber fraud helpline.
- **Call recordings:** a recorded call is transcribed with the two speakers separated, so the caller's tricks are caught.
- **Ask Kavach (voice assistant):** "Show my suspicious messages", "Read my latest alerts", answered only from the user's real history.
- **Any language in, any language out:** a Hindi scam can be explained in Telugu for a parent or grandparent.
- **History:** every checked message is saved, filterable as fraudulent, suspicious or genuine, with "Explain aloud".

## How Gnani AI is used
| Gnani model | Role in Kavach |
|---|---|
| **Prisma** (speech-to-text) | Voice notes, spoken questions and voice commands (REST); long call recordings with **speaker separation, emotion tags and denoise** for noisy phone audio (Batch); domain keyterms such as CBI, OTP, KYC, AnyDesk |
| **Timbre** (text-to-speech) | Spoken verdicts and warnings in the user's language, the voice assistant's replies, and the phone's spoken scam alerts |

## How it works
Input (text / voice / call) → **Gnani Prisma** transcript → multilingual keyword safety layer (warning vs. real request,
e.g. "do not share your OTP" is not a scam) → LLM reasoning over verified Indian scam playbooks → verdict with verbatim
evidence → **Gnani Timbre** voice reply.

## Why it matters
- Built for the people scammers target most: **regional-language and Hinglish** speakers, often elderly.
- Avoids false alarms on genuine bank OTPs and alerts, so users keep trusting the warnings.
- Works on **noisy telephonic audio**, where the most dangerous scams happen.
- Always points to real help: **1930** and **cybercrime.gov.in**.

## Tech
FastAPI (Python) · Gnani Prisma and Timbre · LLM via an OpenAI-compatible API (Groq) · Android (Kotlin, Jetpack Compose,
NotificationListenerService) · web app · deployed on Render · 74 automated tests and a 56-case scam benchmark.

**Next:** move reasoning to Gnani's **Evon** model, add live call-audio checks, and add more regional scam playbooks.
