"""Write the keyword rules to the Android app's assets (used by CI and by hand).

  py -m scripts.export_rules
"""
import json
from pathlib import Path

from app.scam_kb import export_rules

OUT = Path(__file__).resolve().parent.parent / "android" / "app" / "src" / "main" / "assets" / "rules.json"

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(export_rules(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT} ({len(export_rules()['rules'])} rules)")
