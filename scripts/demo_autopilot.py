"""Autopilot demo: drives the LIVE Kavach website by itself, with captions and a spoken voice-over,
for screen recording. Target length: 2-3 minutes.

Everything shown is real: real AI verdicts and real Gnani voices from your server.
  - Narrator: Gnani Timbre voice "Avinash" (different from Kavach's own voice, "Lakshmi").
  - Kavach's own spoken replies are played as short clips to keep the video tight.
  - A call recording (optional) is analysed BEFORE recording starts and shown from History,
    so the video has no transcription wait.

One-time setup (on your laptop):
  uv run --with playwright playwright install chromium

Run:
  uv run --with playwright python -m scripts.demo_autopilot --recording "C:\\path\\to\\scam_call.m4a"
  uv run --with playwright python -m scripts.demo_autopilot                    # without the call
Options: --narrator Avinash  --speed 1.08  --no-voiceover  --url http://localhost:8000
"""
import argparse
import base64
import mimetypes
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

SMS_SCAM = ("Dear Consumer, your electricity power will be disconnected tonight at 9.30 PM because your previous "
            "month bill was not updated. Please immediately contact our electricity officer 9876543210.")
SMS_SAFE = "Your OTP for login is 482913. Valid for 5 minutes. Do not share this OTP with anyone. Bank never asks for OTP. -SBI"
SMS_HINDI = ("मैं सीबीआई से बोल रहा हूँ। आपके आधार पर मनी लॉन्ड्रिंग का केस है। अभी डिजिटल अरेस्ट है, "
             "वीडियो कॉल पर रहिए और किसी को मत बताइए। पैसे वेरिफिकेशन अकाउंट में ट्रांसफर कीजिए।")

# Narration: short, punchy, spoken to the viewer. key -> (caption on screen, line the narrator speaks)
N = {
    "intro": ("Kavach Guard · AI scam shield · 11 Indian languages",
              "Okay, real talk. Scammers have taken thousands of crores from Indians with fake calls and messages. "
              "So we built Kavach. Let's see it in action."),
    "sms1": ("A fake electricity-bill SMS",
             "First up, this classic. Your power will be cut tonight, call this number. Let's paste it in."),
    "sms1b": ("Scam caught: exact red flags, facts and what to do",
              "Boom. Scam. High risk, the exact red flags, and what to do next. And it talks back to you."),
    "sms2": ("A genuine bank OTP",
             "But here's the tricky part. A real bank O.T.P. message. It says O.T.P., it says bank."),
    "sms2b": ("Marked safe: no false alarm",
              "And Kavach knows it's just a warning. Safe. No false alarm."),
    "hist": ("Every check saved in History",
             "Every check lands in your history. Filter by fraud, suspicious, or genuine."),
    "call": ("A recorded scam call, analysed by Gnani Prisma",
             "This one's a recorded phone call. Gnani Prisma split the caller from the victim, and Kavach caught the tricks."),
    "open": ("Explain aloud",
             "Tap any message, and hear exactly why it's dangerous."),
    "ask": ("Ask Kavach: voice assistant",
            "Or just ask. Show my suspicious messages."),
    "lang": ("Hindi scam in, Telugu answer out",
             "And the best part? A Hindi digital arrest scam, explained in Telugu. For your parents, in their language."),
    "end": ("Also on Android: automatic shield for every SMS & WhatsApp · Lost money? Call 1930",
            "On Android, it does all this automatically, for every message. Kavach. Your scam shield, in your language."),
}

CAPTION_JS = """
(text) => {
  let el = document.getElementById('demoCaption');
  if (!el) {
    el = document.createElement('div'); el.id = 'demoCaption';
    el.style.cssText = 'position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:9999;max-width:min(880px,92vw);' +
      'padding:12px 22px;border-radius:16px;background:rgba(124,92,255,.95);color:#fff;font:700 18px/1.4 system-ui,sans-serif;' +
      'box-shadow:0 10px 40px rgba(0,0,0,.5);text-align:center;transition:opacity .3s;pointer-events:none';
    document.body.appendChild(el);
  }
  el.style.opacity = text ? '1' : '0'; if (text) el.textContent = text;
}
"""
NARRATE_JS = """
async ([text, url, voice, speed]) => {
  window.__narr = window.__narr || {};
  if (!window.__narr[text]) {
    const fd = new FormData(); fd.append('text', text); fd.append('language', 'en-IN');
    fd.append('voice', voice); fd.append('speed', String(speed));
    const r = await fetch(url + '/api/speak', { method: 'POST', body: fd });
    if (!r.ok) return false;
    window.__narr[text] = URL.createObjectURL(await r.blob());
  }
  return true;
}
"""
PLAY_JS = """
async (text) => {
  const src = (window.__narr || {})[text]; if (!src) return false;
  const a = new Audio(src);
  await a.play();
  await new Promise(res => { a.onended = res; a.onerror = res; });
  return true;
}
"""
STOP_AUDIO_JS = """() => {
  document.querySelectorAll('audio').forEach(a => a.pause());
  if (typeof player !== 'undefined' && player) player.pause();
}"""
PLAYING_JS = ("() => [...document.querySelectorAll('audio')].some(a => !a.paused && !a.ended)"
              " || (typeof player !== 'undefined' && player && !player.paused && !player.ended)")
PRELOAD_CALL_JS = """
async ([b64, name, mime, url]) => {
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const fd = new FormData();
  fd.append('audio', new Blob([bytes], { type: mime }), name);
  fd.append('output', 'text'); fd.append('reply_language', 'auto');
  const r = await fetch(url + '/api/message', { method: 'POST', body: fd });
  const d = await r.json().catch(() => ({ error: 'server error ' + r.status }));
  if (d.error) return d.error;
  saveRecord(d, '', { name });
  return '';
}
"""
VOICEOVER = {"on": True}


def caption(page: Page, key: str, hold: float = 0):
    """Show a caption; with voice-over on, the narrator speaks the line and we wait until it finishes."""
    cap, line = N.get(key, (key, ""))
    page.evaluate(CAPTION_JS, cap)
    spoken = False
    if line and VOICEOVER["on"]:
        try:
            spoken = bool(page.evaluate(PLAY_JS, line))
        except Exception:
            spoken = False
    if not spoken and hold:
        time.sleep(hold)


def prepare_voiceover(page: Page, url: str, voice: str, speed: float) -> int:
    """Generate every narration line with Gnani Timbre BEFORE recording, so the video has no gaps."""
    ok = 0
    lines = [line for _, line in N.values()]
    for i, line in enumerate(lines, 1):
        print(f"  voice-over {i}/{len(lines)}…", end="\r", flush=True)
        try:
            ok += bool(page.evaluate(NARRATE_JS, [line, url, voice, speed]))
        except Exception as e:
            print("\n  voice-over line failed:", str(e)[:120])
    print(f"  voice-over ready: {ok}/{len(lines)} lines (Gnani Timbre, voice {voice})        ")
    return ok


def type_fast(page: Page, selector: str, text: str):
    page.click(selector)
    page.fill(selector, "")
    page.keyboard.type(text, delay=8)


def voice_clip(page: Page, seconds: float):
    """Let Kavach's own spoken reply play for a short clip, then stop it (keeps the video short)."""
    end = time.time() + seconds
    time.sleep(0.8)
    while time.time() < end and page.evaluate(PLAYING_JS):
        time.sleep(0.3)
    page.evaluate(STOP_AUDIO_JS)


def set_output(page: Page, mode: str):
    page.click(f"#outSeg [data-v={mode}]")


def analyse(page: Page, text: str, timeout_s: int = 120):
    count = page.locator("#feed .gauge, #feed .answer, #feed .err").count()
    type_fast(page, "#text", text)
    page.click("#send")
    page.wait_for_function(
        "(n) => document.querySelectorAll('#feed .gauge, #feed .answer, #feed .err').length > n", arg=count,
        timeout=timeout_s * 1000)
    if page.locator("#feed .err").count():
        print("Server said:", page.locator("#feed .err").last.inner_text())
    page.locator("#feed > div").last.scroll_into_view_if_needed()


def scroll_result(page: Page, seconds: float):
    for _ in range(int(seconds / 0.35)):
        page.mouse.wheel(0, 140)
        time.sleep(0.35)


def run(url: str, recording: str | None, wake: bool, narrator: str, speed: float):
    url = url.rstrip("/")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, args=["--start-maximized", "--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page(no_viewport=True)
        if wake:
            print("Waking the server (free plan can take ~50 s)…")
            page.request.get(url + "/health", timeout=120_000)
        page.goto(url, timeout=120_000)
        page.evaluate("() => { localStorage.removeItem('kavach.records'); localStorage.setItem('kavach.output', 'both');"
                      " localStorage.setItem('kavach.lang', 'auto'); }")
        page.reload()
        if not page.locator("[data-tab=history]").count():
            browser.close()
            raise SystemExit("This server still has the OLD website (no History / Ask tabs).\n"
                             "On Render: kavach service -> Manual Deploy -> Deploy latest commit, wait for 'Live', then run this again.")

        call_ready = False
        if recording:
            print("Analysing the call recording now, before recording starts (can take 1-2 minutes)…")
            data = Path(recording).read_bytes()
            mime = mimetypes.guess_type(recording)[0] or "application/octet-stream"
            err = page.evaluate(PRELOAD_CALL_JS, [base64.b64encode(data).decode(), Path(recording).name, mime, url])
            if err:
                print("  Call analysis failed, skipping that part:", err[:200])
            else:
                call_ready = True
                print("  Call analysed and saved to History.")

        if VOICEOVER["on"]:
            print(f"Preparing the voice-over (Gnani Timbre, narrator {narrator})…")
            if not prepare_voiceover(page, url, narrator, speed):
                print("  Voice-over unavailable (server or Gnani error): captions only.")
                VOICEOVER["on"] = False

        input("\nStart your screen recorder now (Win + Alt + R), then press Enter here to begin the demo… ")
        page.bring_to_front()
        t0 = time.time()

        caption(page, "intro", 6)

        # 1. scam SMS, with a short clip of Kavach's own voice
        caption(page, "sms1", 4)
        set_output(page, "both")
        analyse(page, SMS_SCAM)
        voice_clip(page, 7)
        caption(page, "sms1b", 4)
        scroll_result(page, 2.5)

        # 2. genuine OTP: text only, fast
        caption(page, "sms2", 4)
        set_output(page, "text")
        analyse(page, SMS_SAFE)
        caption(page, "sms2b", 3)

        # 3. History, the pre-analysed call, explain aloud
        page.click("[data-tab=history]")
        caption(page, "hist", 3)
        page.click("#pills [data-f=fraud]")
        time.sleep(1)
        page.click("#pills [data-f=genuine]")
        time.sleep(1)
        page.click("#pills [data-f=all]")
        time.sleep(0.6)
        if call_ready:
            calls = page.locator("#list .recrow", has_text="Call recording")
            if calls.count():
                calls.first.click()
                time.sleep(1)
                caption(page, "call", 4)
                page.mouse.wheel(0, 500)
                time.sleep(1.5)
                page.click("#closeDetail")
        page.click("#pills [data-f=fraud]")
        time.sleep(0.6)
        page.locator("#list .recrow").first.click()
        time.sleep(1)
        caption(page, "open", 3)
        page.click("#explainBtn")
        page.wait_for_function("() => (document.querySelector('#explainOut')?.textContent || '').trim().length > 0",
                               timeout=90_000)
        voice_clip(page, 7)
        page.click("#closeDetail")

        # 4. Ask Kavach: one command
        page.click("[data-tab=ask]")
        caption(page, "ask", 3)
        page.click("[data-cmd='Show my suspicious messages']")
        page.wait_for_function("() => !document.querySelector('#askMic').disabled", timeout=90_000)
        voice_clip(page, 8)

        # 5. Hindi in, Telugu out
        page.click("[data-tab=check]")
        caption(page, "lang", 4)
        page.select_option("#lang", "te-IN")
        set_output(page, "both")
        analyse(page, SMS_HINDI)
        voice_clip(page, 7)
        scroll_result(page, 2)
        page.select_option("#lang", "auto")

        caption(page, "end", 5)
        time.sleep(1.5)
        caption(page, "")
        took = time.time() - t0
        print(f"\nDemo length: {int(took // 60)}:{int(took % 60):02d}")
        input("Demo finished. Stop the recorder (Win + Alt + R), then press Enter to close the browser… ")
        browser.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="https://kavach-yqti.onrender.com")
    ap.add_argument("--recording", help="optional call recording (m4a/mp3/wav…), analysed before recording starts")
    ap.add_argument("--narrator", default="Avinash", help="Gnani Timbre voice for the narration (Kavach itself uses Lakshmi)")
    ap.add_argument("--speed", type=float, default=1.08, help="narration speed, 0.8-1.3 (default 1.08: lively)")
    ap.add_argument("--no-wake", action="store_true", help="skip the server wake-up call")
    ap.add_argument("--no-voiceover", action="store_true", help="captions only, no spoken narration")
    a = ap.parse_args()
    if a.recording:
        rec = Path(a.recording.strip('"')).expanduser()
        if not rec.is_file():
            raise SystemExit(f"Recording not found: {rec.resolve()}\n"
                             "Tip: in File Explorer, Shift + right-click the file -> 'Copy as path', and paste it after --recording.")
        a.recording = str(rec.resolve())
    VOICEOVER["on"] = not a.no_voiceover
    run(a.url, a.recording, not a.no_wake, a.narrator, a.speed)


if __name__ == "__main__":
    main()
