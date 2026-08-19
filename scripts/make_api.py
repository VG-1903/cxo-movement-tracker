"""Generate the static JSON API under api/v1/ from data/moves_master.json.

Endpoints (all CORS-open when served from GitHub Pages):
    api/v1/index.json      catalog + stats
    api/v1/all.json        every record
    api/v1/bfsi.json       BFSI only
    api/v1/pharma.json     Pharma & Healthcare only
    api/v1/education.json  Education only
    api/v1/corporate.json  Corporate only
Each sector file also gets a *_latest.json with the 50 most recent records.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "moves_master.json"
API = ROOT / "api" / "v1"

SECTORS = {
    "bfsi": "BFSI",
    "pharma": "Pharma & Healthcare",
    "education": "Education",
    "corporate": "Corporate",
}
FIELDS = ["date", "person", "movement", "role", "company", "sector", "region",
          "publisher", "headline", "link", "also_reported_by"]


def payload(slug, label, records, updated):
    return {
        "api_version": "1",
        "source": "CXO Movement Tracker",
        "sector": label,
        "updated": updated,
        "count": len(records),
        "records": [{k: r.get(k, "") for k in FIELDS} for r in records],
    }


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")


def main():
    recs = json.loads(DATA.read_text(encoding="utf-8"))
    updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    API.mkdir(parents=True, exist_ok=True)

    write(API / "all.json", payload("all", "All sectors", recs, updated))
    write(API / "all_latest.json", payload("all", "All sectors", recs[:50], updated))

    stats = {"all": len(recs)}
    for slug, label in SECTORS.items():
        sub = [r for r in recs if r["sector"] == label]
        stats[slug] = len(sub)
        write(API / f"{slug}.json", payload(slug, label, sub, updated))
        write(API / f"{slug}_latest.json", payload(slug, label, sub[:50], updated))

    write(API / "index.json", {
        "api_version": "1",
        "source": "CXO Movement Tracker",
        "updated": updated,
        "counts": stats,
        "endpoints": ["all.json", "all_latest.json"] + sorted(
            f"{s}{suf}.json" for s in SECTORS for suf in ("", "_latest")),
        "record_fields": FIELDS,
        "movement_types": ["Appointment", "Promotion", "Re-appointment",
                           "Resignation", "Retirement"],
        "regions": ["India", "Global"],
    })
    print(f"api: {API}  counts={stats}")


if __name__ == "__main__":
    main()
