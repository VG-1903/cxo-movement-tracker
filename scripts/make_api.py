"""Generate the static JSON API under api/v1/ from data/moves_master.json.

Endpoints (all CORS-open when served from GitHub Pages):
    api/v1/index.json      catalog + stats
    api/v1/all.json        every record
    api/v1/bfsi.json       BFSI only
    api/v1/pharma.json     Pharma & Healthcare only
    api/v1/education.json  Education only
    api/v1/corporate.json  Corporate only
    api/v1/corporate_ceo.json, _cfo, _cmo, _cdo …  Corporate split by role group
Each sector/role file also gets a *_latest.json with the 50 most recent records.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parser_lib import ROLE_GROUPS

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "moves_master.json"
API = ROOT / "api" / "v1"

SECTORS = {
    "bfsi": "BFSI",
    "pharma": "Pharma & Healthcare",
    "education": "Education",
    "corporate": "Corporate",
}
# Corporate is additionally split by role group (CEO / CFO / CMO / CDO …), since
# "who moved" matters as much as "which industry" for the general-corporate feed.
# Academic Leadership is an Education construct, so it gets no corporate endpoint.
ROLE_ENDPOINTS = [(slug, label) for label, slug, _ in ROLE_GROUPS
                  if label != "Academic Leadership"]
# source attribution (publisher, link, outlet list) is intentionally NOT exposed
# via the API — it stays on the dashboard only. source_count keeps the
# how-many-outlets-reported-this confidence signal without naming them.
FIELDS = ["date", "person", "movement", "role", "role_group", "company",
          "moved_from", "moved_from_source", "sector", "region", "headline"]


def payload(label, records, updated, role_group=None):
    out = {
        "api_version": "1",
        "source": "CXO Movement Tracker",
        "sector": label,
    }
    if role_group:
        out["role_group"] = role_group
    out.update({
        "updated": updated,
        "count": len(records),
        "records": [
            {**{k: r.get(k, "") for k in FIELDS},
             "source_count": 1 + len(r.get("also_reported_by", []))}
            for r in records
        ],
    })
    return out


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")


def main():
    recs = json.loads(DATA.read_text(encoding="utf-8"))
    updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    API.mkdir(parents=True, exist_ok=True)

    write(API / "all.json", payload("All sectors", recs, updated))
    write(API / "all_latest.json", payload("All sectors", recs[:50], updated))

    stats = {"all": len(recs)}
    for slug, label in SECTORS.items():
        sub = [r for r in recs if r["sector"] == label]
        stats[slug] = len(sub)
        write(API / f"{slug}.json", payload(label, sub, updated))
        write(API / f"{slug}_latest.json", payload(label, sub[:50], updated))

    corporate = [r for r in recs if r["sector"] == "Corporate"]
    role_stats = {}
    for slug, role in ROLE_ENDPOINTS:
        sub = [r for r in corporate if r.get("role_group") == role]
        role_stats[slug] = len(sub)
        write(API / f"corporate_{slug}.json",
              payload("Corporate", sub, updated, role_group=role))
        write(API / f"corporate_{slug}_latest.json",
              payload("Corporate", sub[:50], updated, role_group=role))

    write(API / "index.json", {
        "api_version": "1",
        "source": "CXO Movement Tracker",
        "updated": updated,
        "counts": stats,
        "corporate_by_role": role_stats,
        "endpoints": ["all.json", "all_latest.json"] + sorted(
            [f"{s}{suf}.json" for s in SECTORS for suf in ("", "_latest")] +
            [f"corporate_{slug}{suf}.json" for slug, _ in ROLE_ENDPOINTS
             for suf in ("", "_latest")]),
        "record_fields": FIELDS + ["source_count"],
        "movement_types": ["Appointment", "Promotion", "Re-appointment",
                           "Resignation", "Retirement"],
        "role_groups": {slug: role for slug, role in ROLE_ENDPOINTS},
        "regions": ["India", "Global"],
    })
    print(f"api: {API}  counts={stats}")
    print("corporate by role:", json.dumps(role_stats))


if __name__ == "__main__":
    main()
