"""Run the realistic fraud test suite (tests/cases.json) and write a report.

Usage (from the project root):
  py -m scripts.run_tests --offline            # keyword layer only, no API calls, instant
  py -m scripts.run_tests                      # full AI verdicts (Groq), ~3 s between cases
  py -m scripts.run_tests --only DA-1 SAFE-4   # selected cases
  py -m scripts.run_tests --category upi       # cases whose category contains "upi"
  py -m scripts.run_tests --audio --only DA-1  # speak with Gnani TTS -> transcribe -> analyse (uses credits)

Reports: tests/report.md and tests/results.json
"""
import argparse
import asyncio
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from app import gnani
from app.analyzer import Session
from app.scam_kb import scan

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "tests" / "cases.json"
SCAM_VERDICTS = {"SCAM", "LIKELY_SCAM"}


def load(args) -> list[dict]:
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    if args.only:
        wanted = {i.upper() for i in args.only}
        cases = [c for c in cases if c["id"].upper() in wanted]
    if args.category:
        cases = [c for c in cases if args.category.lower() in c["category"].lower()]
    return cases


def is_scam_case(c: dict) -> bool:
    return bool(SCAM_VERDICTS & set(c["expect"]["verdicts"])) and c["category"] != "None"


# ------------------------------------------------------------------ offline (keyword layer)

def run_offline(cases: list[dict]) -> int:
    rows, problems = [], 0
    for c in cases:
        s = scan(c["text"])
        safe_case = not is_scam_case(c)
        flag = ""
        if safe_case and s["risk_floor"] >= 35:
            flag, problems = "FALSE ALARM: floor forces >= SUSPICIOUS", problems + 1
        elif not safe_case and s["risk_floor"] == 0:
            flag = "no keyword hits (relies on AI only)"
        rows.append((c["id"], c["language"], s["risk_floor"], s["score"],
                     ", ".join(h["label"] for h in s["hits"])[:90], flag))
    print(f"{'ID':8} {'lang':6} {'floor':>5} {'score':>5}  flags")
    for r in rows:
        print(f"{r[0]:8} {r[1]:6} {r[2]:>5} {r[3]:>5}  {r[4]}" + (f"\n{'':28}-> {r[5]}" if r[5] else ""))
    print(f"\n{len(cases)} cases, {problems} keyword-layer false alarm(s) on safe cases.")
    return problems


# ------------------------------------------------------------------ live

async def llm_with_retry(session: Session, text: str, **kw) -> dict:
    for attempt in range(4):
        try:
            return await session.respond(text, **kw)
        except Exception as e:  # Groq rate limit (429) or a transient error
            msg = str(e)
            if attempt == 3 or not re.search(r"429|rate|timeout|temporar|5\d\d", msg, re.I):
                raise
            wait = 15 * (attempt + 1)
            print(f"    LLM busy ({msg[:60]}...), retrying in {wait}s")
            await asyncio.sleep(wait)


def speakable(text: str) -> str:
    return re.sub(r"^Speaker \d+:\s*", "", text, flags=re.M)


def check(c: dict, r: dict) -> list[str]:
    exp, fails = c["expect"], []
    if r.get("verdict") not in exp["verdicts"]:
        fails.append(f"verdict {r.get('verdict')} not in {exp['verdicts']}")
    kws = exp.get("type_keywords")
    if kws and not any(k.lower() in str(r.get("scam_type", "")).lower() for k in kws):
        fails.append(f"type '{r.get('scam_type')}' lacks {kws}")
    if exp.get("language") and r.get("language") != exp["language"]:
        fails.append(f"replied in {r.get('language')} not {exp['language']}")
    return fails


async def run_case(c: dict, audio: bool) -> dict:
    session, t0 = Session(), time.perf_counter()
    text, source, stt_lang, segments, heard = c["text"], c["channel"], c["language"], None, None
    if audio:
        lang = c["language"] if c["language"] != "hi-en" else "hi-en"
        wav = await gnani.synthesize(speakable(text), lang, sample_rate=16000)
        stt = await gnani.transcribe(wav, f"{c['id']}.wav")
        text, stt_lang, segments, heard = stt["transcript"], stt["language"], stt["segments"], stt["transcript"]
        source = f"{c['channel']} (spoken, {stt['engine']} STT)"
    r = await llm_with_retry(session, text, source=source, stt_language=stt_lang,
                             reply_language=c.get("reply_language", "auto"), signals=scan(text, segments))
    out = {"id": c["id"], "result": r, "fails": check(c, r), "heard": heard}

    fu = c.get("followup")
    if fu:
        await asyncio.sleep(2)
        f = await llm_with_retry(session, fu["text"], source="text message", stt_language=None,
                                 reply_language=c.get("reply_language", "auto"), signals=scan(fu["text"]))
        blob = " ".join([str(f.get("summary")), str(f.get("spoken")), " ".join(map(str, f.get("actions", [])))]).lower()
        if f.get("kind") != fu.get("expect_kind", "answer"):
            out["fails"].append(f"follow-up kind {f.get('kind')} not {fu.get('expect_kind', 'answer')}")
        if not any(m.lower() in blob for m in fu.get("must_mention_any", [])):
            out["fails"].append(f"follow-up doesn't mention any of {fu['must_mention_any']}")
        out["followup"] = f
    out["ms"] = round((time.perf_counter() - t0) * 1000)
    return out


def write_report(cases: list[dict], results: list[dict], audio: bool) -> str:
    by_id = {c["id"]: c for c in cases}
    passed = [x for x in results if not x["fails"] and not x.get("error")]
    scam = [x for x in results if is_scam_case(by_id[x["id"]])]
    safe = [x for x in results if not is_scam_case(by_id[x["id"]])]
    detected = [x for x in scam if x.get("result", {}).get("verdict") in SCAM_VERDICTS | {"SUSPICIOUS"}]
    false_alarms = [x for x in safe if x.get("result", {}).get("verdict") in SCAM_VERDICTS | {"SUSPICIOUS"}]

    def pct(a, b):
        return f"{(100 * len(a) / len(b)):.0f}%" if b else "-"

    lines = [
        f"# Kavach test report{' (audio pipeline)' if audio else ''}",
        "",
        f"- **Passed:** {len(passed)}/{len(results)} ({pct(passed, results)})",
        f"- **Scams caught** (SCAM / LIKELY_SCAM / SUSPICIOUS): {len(detected)}/{len(scam)} ({pct(detected, scam)})",
        f"- **False alarms on safe messages:** {len(false_alarms)}/{len(safe)} ({pct(false_alarms, safe)})",
        f"- **Average time per case:** {sum(x.get('ms', 0) for x in results) // max(1, len(results))} ms",
        "",
        "## By fraud type",
        "| Category | Passed |",
        "|---|---|",
    ]
    cats = defaultdict(list)
    for x in results:
        cats[by_id[x["id"]]["category"]].append(x)
    for cat, xs in cats.items():
        lines.append(f"| {cat if cat != 'None' else 'Safe / edge (no scam)'} | {sum(not x['fails'] and not x.get('error') for x in xs)}/{len(xs)} |")

    lines += ["", "## All cases",
              "| ID | Lang | Channel | Difficulty | Expected | Got | Type returned | Reply lang | Result |",
              "|---|---|---|---|---|---|---|---|---|"]
    for x in results:
        c, r = by_id[x["id"]], x.get("result", {})
        status = "✅" if not x["fails"] and not x.get("error") else "❌ " + "; ".join(x["fails"] or [x.get("error", "")])
        lines.append(f"| {c['id']} | {c['language']} | {c['channel']} | {c['difficulty']} | {'/'.join(c['expect']['verdicts'])} | "
                     f"{r.get('verdict', 'ERROR')} ({r.get('risk_score', '-')}) | {r.get('scam_type', '-')} | {r.get('language', '-')} | {status} |")

    lines += ["", "## Failures in detail"]
    for x in results:
        if x["fails"] or x.get("error"):
            c, r = by_id[x["id"]], x.get("result", {})
            lines += [f"### {c['id']} ({c['category']})", f"- Notes: {c['notes']}",
                      f"- Problems: {'; '.join(x['fails']) or x.get('error')}",
                      f"- Summary given: {r.get('summary', '-')}", ""]
            if x.get("heard"):
                lines.append(f"- Transcript heard: {x['heard'][:300]}")
    return "\n".join(lines) + "\n"


async def run_live(cases: list[dict], args) -> int:
    results = []
    for i, c in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {c['id']:8} {c['language']:6} {c['category'][:34]:34}", end=" ", flush=True)
        try:
            x = await run_case(c, args.audio)
            r = x["result"]
            print(f"{r.get('verdict'):16} {r.get('risk_score'):>3}  {'PASS' if not x['fails'] else 'FAIL: ' + '; '.join(x['fails'])}")
        except Exception as e:
            x = {"id": c["id"], "fails": [], "error": f"{type(e).__name__}: {str(e)[:200]}"}
            print("ERROR", x["error"])
        results.append(x)
        if i < len(cases):
            await asyncio.sleep(args.delay)

    report = write_report(cases, results, args.audio)
    (ROOT / "tests" / "report.md").write_text(report, encoding="utf-8")
    (ROOT / "tests" / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + "\n".join(report.splitlines()[:6]))
    print("Full report: tests/report.md")
    return sum(bool(x["fails"] or x.get("error")) for x in results)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="keyword layer only, no API calls")
    ap.add_argument("--audio", action="store_true", help="speak each case with Gnani TTS and transcribe it first")
    ap.add_argument("--only", nargs="*", help="case IDs to run")
    ap.add_argument("--category", help="run cases whose category contains this text")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between cases (rate limits)")
    args = ap.parse_args()
    cases = load(args)
    if not cases:
        raise SystemExit("No matching cases.")
    if args.offline:
        raise SystemExit(1 if run_offline(cases) else 0)
    raise SystemExit(1 if asyncio.run(run_live(cases, args)) else 0)


if __name__ == "__main__":
    main()
