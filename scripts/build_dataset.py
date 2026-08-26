"""Parse raw items into movement records, dedupe, write data/moves_master.json + output/moves.csv."""
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parser_lib import (extract_all, extract_moved_from, region_of,
                        role_group_of, sector_of)
from dedupe_lib import dedupe

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "items.jsonl"
OUT_JSON = ROOT / "data" / "moves_master.json"
OUT_CSV = ROOT / "output" / "moves.csv"


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def merge(moves, rec):
    # dedupe on person+company+movement (same story from many outlets);
    # if company missing, fall back to person+movement so bare reprints still merge
    k = (norm(rec["person"]), norm(rec["company"]), rec["movement"])
    prev = moves.get(k)
    if prev is None:
        rec["also_reported_by"] = []
        moves[k] = rec
        return
    if rec["publisher"] and rec["publisher"] != prev["publisher"] \
            and rec["publisher"] not in prev["also_reported_by"]:
        prev["also_reported_by"].append(rec["publisher"])
    if rec["date"] and (not prev["date"] or rec["date"] < prev["date"]):
        prev["date"] = rec["date"]
    if not prev["company"] and rec["company"]:
        prev["company"] = rec["company"]
    if not prev["moved_from"] and rec["moved_from"]:
        prev["moved_from"] = rec["moved_from"]
        prev["moved_from_source"] = rec["moved_from_source"]
    if prev["region"] == "Global" and rec["region"] == "India":
        prev["region"] = "India"


def main():
    items, seen_titles = [], set()
    for line in RAW.read_text(encoding="utf-8").splitlines():
        try:
            it = json.loads(line)
        except Exception:
            continue
        if it["key"] in seen_titles:
            continue
        seen_titles.add(it["key"])
        items.append(it)

    moves, misses = {}, 0
    for it in items:
        recs = extract_all(it["title"])
        if not recs:
            misses += 1
            continue
        title_base = it["title"].rsplit(" - ", 1)[0] if " - " in it["title"] else it["title"]
        for rec in recs:
            frm = extract_moved_from(it["title"], rec["company"])
            rec.update({
                "role_group": role_group_of(rec["role"]),
                "sector": sector_of(it["title"], it["sector_hint"], rec["company"]),
                "region": region_of(it["title"], it.get("publisher", ""), rec["company"]),
                "date": it.get("date", ""),
                "headline": title_base.strip(),
                "publisher": it.get("publisher", ""),
                "link": it.get("link", ""),
                "moved_from": frm,
                "moved_from_source": "headline" if frm else "",
            })
            merge(moves, rec)

    out = sorted(moves.values(), key=lambda r: r["date"] or "0000", reverse=True)

    # entity-resolution dedupe: name variants, company variants, junk companies,
    # and same-event stories reported with different movement verbs
    out, merged_away = dedupe(out)

    # cross-reference pass: an Appointment by someone whose exit we also tracked
    # at a different company inherits that company as moved_from
    exits = {}
    for r in out:
        if r["movement"] in ("Resignation", "Retirement") and r["company"]:
            exits.setdefault(norm(r["person"]), []).append(r)
    filled = 0
    for r in out:
        if r["movement"] in ("Appointment", "Promotion") and not r["moved_from"]:
            for ex in exits.get(norm(r["person"]), []):
                if norm(ex["company"]) != norm(r["company"]) and \
                        (not r["date"] or not ex["date"] or ex["date"] <= r["date"]):
                    r["moved_from"] = ex["company"]
                    r["moved_from_source"] = "cross-reference"
                    filled += 1
                    break
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    cols = ["date", "person", "movement", "role", "role_group", "company",
            "moved_from", "moved_from_source", "sector", "region", "publisher",
            "headline", "link"]
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)

    by_sector = {}
    for r in out:
        by_sector[r["sector"]] = by_sector.get(r["sector"], 0) + 1
    print(f"raw items: {len(items)}  parsed moves: {len(out)}  "
          f"(dedupe removed {merged_away})  unparsed titles: {misses}")
    print("by sector:", json.dumps(by_sector))
    india = sum(1 for r in out if r["region"] == "India")
    print(f"India: {india}  Global: {len(out) - india}")
    frm_head = sum(1 for r in out if r["moved_from_source"] == "headline")
    print(f"moved_from: {frm_head} from headlines + {filled} cross-referenced "
          f"= {frm_head + filled}/{len(out)}")


if __name__ == "__main__":
    main()
