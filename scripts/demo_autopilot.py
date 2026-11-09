"""Autopilot demo: drives the LIVE Kavach website by itself, with on-screen captions, for screen recording.

Everything shown is real: real AI verdicts and real Gnani voices from your server.
You only start the screen recorder (Windows: Win + Alt + R) and run this.

One-time setup (on your laptop):
  uv run --with playwright playwright install chromium

Run:
  uv run --with playwright python -m scripts.demo_autopilot
  uv run --with playwright python -m scripts.demo_autopilot --recording "C:\\path\\to\\scam_call.m4a"
  uv run --with playwright python -m scripts.demo_autopilot --url http://localhost:8000

Total length is about 3 minutes. Narration is spoken by Gnani Timbre (via your server's /api/speak);
use --no-voiceover for captions only.
"""
import argparse
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

SMS_SCAM = ("Dear Consumer, your electricity power will be disconnected tonight at 9.30 PM because your previous "
            "month bill was not updated. Please immediately contact our electricity officer 9876543210.")
SMS_SAFE = "Your OTP for login is 482913. Valid for 5 minutes. Do not share this OTP with anyone. Bank never asks for OTP. -SBI"
SMS_HINDI = ("मैं सीबीआई से बोल रहा हूँ। आपके आधार पर मनी लॉन्ड्रिंग का केस है। अभी डिजिटल अरेस्ट है, "
             "वीडियो कॉल पर रहिए और किसी को मत बताइए। पैसे वेरिफिकेशन अकाउंट में ट्रांसफर कीजिए।")

CAPTION_JS = """
(text) => {
  let el = document.getElementById('demoCaption');
  if (!el) {
    el = document.createElement('div'); el.id = 'demoCaption';
    el.style.cssText = 'position:fixed;left:50%;top:14px;transform:translateX(-50%);z-index:9999;max-width:min(880px,92vw);' +
      'padding:12px 20px;border-radius:16px;background:rgba(124,92,255,.95);color:#fff;font:600 17px/1.4 system-ui,sans-serif;' +
      'box-shadow:0 10px 40px rgba(0,0,0,.5);text-align:center;transition:opacity .3s';
    document.body.appendChild(el);
  }
  el.style.opacity = text ? '1' : '0'; if (text) el.textContent = text;
}
"""


NARRATE_JS = """
async ([text, url]) => {
  window.__narr = window.__narr || {};
  if (!window.__narr[text]) {
    const fd = new FormData(); fd.append('text', text); fd.append('language', 'en-IN');
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
  const a = new Audio(src); a.volume = 1;
  await a.play();
  await new Promise(res => { a.onended = res; a.onerror = res; });
  return true;
}
"""
VOICEOVER = {"on": True, "url": ""}


def prepare_voiceover(page: Page, url: str, lines: list[str]):
    """Generate every narration line with Gnani Timbre BEFORE recording, so the video has no gaps."""
    ok = 0
    for i, line in enumerate(lines, 1):
        print(f"  voice-over {i}/{len(lines)}…", end="\r", flush=True)
        try:
            ok += bool(page.evaluate(NARRATE_JS, [line, url]))
        except Exception as e:
            print("\n  voice-over line failed:", str(e)[:120])
    print(f"  voice-over ready: {ok}/{len(lines)} lines (Gnani Timbre)        ")
    return ok


def caption(page: Page, text: str, hold: float = 0):
    """Show the caption and, with voice-over on, speak it (Gnani Timbre) and wait until it finishes."""
    page.evaluate(CAPTION_JS, text)
    spoken = False
    if text and VOICEOVER["on"]:
        try:
            spoken = bool(page.evaluate(PLAY_JS, text))
        except Exception:
            spoken = False
    if hold and not spoken:
        time.sleep(hold)
    elif spoken:
        time.sleep(0.4)


def type_slowly(page: Page, selector: str, text: str):
    page.click(selector)
    page.fill(selector, "")
    page.keyboard.type(text, delay=18)


def wait_voice(page: Page, limit: float = 25):
    """Let Kavach's spoken reply finish before moving on."""
    end = time.time() + limit
    time.sleep(1.5)
    while time.time() < end:
        playing = page.evaluate("() => [...document.querySelectorAll('audio')].some(a => !a.paused && !a.ended)"
                                " || (typeof player !== 'undefined' && player && !player.paused && !player.ended)")
        if not playing:
            return
        time.sleep(0.5)


def analyse(page: Page, text: str | None = None, file: str | None = None, timeout_s: int = 180):
    count = page.locator("#feed .gauge, #feed .answer, #feed .err").count()
    if text:
        type_slowly(page, "#text", text)
    if file:
        page.set_input_files("#file", file)
    time.sleep(0.8)
    page.click("#send")
    page.wait_for_function(
        "(n) => document.querySelectorAll('#feed .gauge, #feed .answer, #feed .err').length > n", arg=count,
        timeout=timeout_s * 1000)
    if page.locator("#feed .err").count():
        print("Server said:", page.locator("#feed .err").last.inner_text())
    page.locator("#feed > div").last.scroll_into_view_if_needed()
    time.sleep(1)


def scroll_result(page: Page, seconds: float = 6):
    """Slowly scroll through the newest result card so viewers can read it."""
    steps = int(seconds / 0.4)
    for _ in range(steps):
        page.mouse.wheel(0, 120)
        time.sleep(0.4)


N = {
    "intro": "Meet Kavach Guard. An A.I. scam shield for India, that understands eleven Indian languages, powered by Gnani's speech A.I.",
    "sms1": "First, a fake electricity bill message. One of the most common scams in India.",
    "sms1b": "Kavach flags it as a scam, quotes the exact red flags, gives the facts, and tells you what to do.",
    "sms2": "Next, a real one time password message from a bank. It mentions O.T.P. and bank, but it is only a warning.",
    "sms2b": "So Kavach marks it safe. No false alarm on genuine bank messages.",
    "call": "Now a recorded phone call. Gnani Prisma transcribes it, and separates the caller from the victim.",
    "callb": "Kavach catches the caller's tricks, right inside the conversation.",
    "hist": "Every check is saved in history, with fraud, suspicious and genuine filters.",
    "open": "Open any message to see exactly why, and hear it explained.",
    "ask": "Ask Kavach is a voice assistant. It answers only from your real history.",
    "lang": "Any language in, any language out. Here, a Hindi digital arrest scam, explained in Telugu.",
    "android": "On Android, Kavach Guard does all of this automatically, for every incoming S.M.S. and WhatsApp message. If you have lost money, call one nine three zero.",
    "end": "Kavach. Your scam shield, in your language.",
}


def run(url: str, recording: str | None, wake: bool):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, args=["--start-maximized", "--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page(no_viewport=True)
        page.goto(url, timeout=120_000)
        page.evaluate("() => { localStorage.removeItem('kavach.records'); localStorage.setItem('kavach.output', 'both');"
                      " localStorage.setItem('kavach.lang', 'auto'); }")
        page.reload()
        if wake:
            print("Waking the server (free plan can take ~50 s)…")
            page.request.get(url.rstrip("/") + "/health", timeout=120_000)
        if not page.locator("[data-tab=history]").count():
            browser.close()
            raise SystemExit("This server still has the OLD website (no History / Ask tabs).\n"
                             "On Render: kavach service -> Manual Deploy -> Deploy latest commit, wait for 'Live', then run this again.")
        if VOICEOVER["on"]:
            print("Preparing the voice-over with Gnani Timbre…")
            if not prepare_voiceover(page, url.rstrip("/"), list(N.values())):
                print("  Voice-over unavailable (server or Gnani error): captions only.")
                VOICEOVER["on"] = False
        input("\nStart your screen recorder now (Win + Alt + R), then press Enter here to begin the demo… ")
        page.bring_to_front()

        caption(page, N["intro"], 5)

        caption(page, N["sms1"], 5)
        analyse(page, SMS_SCAM)
        wait_voice(page)
        caption(page, N["sms1b"], 4)
        scroll_result(page, 5)

        caption(page, N["sms2"], 5)
        analyse(page, SMS_SAFE)
        wait_voice(page)
        caption(page, N["sms2b"], 4)
        time.sleep(2)

        if recording:
            caption(page, N["call"], 5)
            analyse(page, file=recording, timeout_s=240)
            wait_voice(page)
            caption(page, N["callb"], 4)
            scroll_result(page, 5)

        caption(page, N["hist"], 5)
        page.click("[data-tab=history]")
        time.sleep(3)
        page.click("#pills [data-f=fraud]")
        time.sleep(2)
        page.click("#pills [data-f=genuine]")
        time.sleep(2)
        page.click("#pills [data-f=fraud]")
        time.sleep(1.5)
        caption(page, N["open"], 5)
        page.click("#list .recrow")
        time.sleep(2.5)
        page.click("#explainBtn")
        page.wait_for_function("() => document.querySelector('#explainOut') && document.querySelector('#explainOut').textContent.trim().length > 0",
                               timeout=90_000)
        wait_voice(page)
        time.sleep(1)
        page.click("#closeDetail")

        caption(page, N["ask"], 5)
        page.click("[data-tab=ask]")
        time.sleep(2)
        for cmd in ("Show my suspicious messages", "Give me a summary of my scanned messages"):
            page.click(f"[data-cmd='{cmd}']")
            page.wait_for_function("() => !document.querySelector('#askMic').disabled", timeout=90_000)
            time.sleep(0.5)
            wait_voice(page)
            time.sleep(1.5)

        caption(page, N["lang"], 5)
        page.click("[data-tab=check]")
        page.select_option("#lang", "te-IN")
        time.sleep(1)
        analyse(page, SMS_HINDI)
        wait_voice(page)
        scroll_result(page, 4)
        page.select_option("#lang", "auto")

        caption(page, N["android"], 5)
        caption(page, N["end"], 5)
        caption(page, "")
        input("\nDemo finished. Stop the recorder (Win + Alt + R), then press Enter to close the browser… ")
        browser.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="https://kavach-yqti.onrender.com")
    ap.add_argument("--recording", help="optional call recording (m4a/mp3/wav…) to show the call check")
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
    run(a.url, a.recording, not a.no_wake)


if __name__ == "__main__":
    main()
