"""Render output/CXO_Moves_Dashboard.html from data/moves_master.json + template."""
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "scripts" / "dashboard_template.html"
DATA = ROOT / "data" / "moves_master.json"
OUT = ROOT / "output" / "CXO_Moves_Dashboard.html"


def main():
    recs = json.loads(DATA.read_text(encoding="utf-8"))
    payload = json.dumps(recs, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__DATA__", payload)
    html = html.replace("__GENERATED__", datetime.now().strftime("%d %b %Y, %H:%M"))
    html = html.replace("__TOTAL__", str(len(recs)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"dashboard: {OUT}  ({len(recs)} records, {OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
