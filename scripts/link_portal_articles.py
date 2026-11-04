"""Link every ticker move to its full article on the Elets portal.

The portal ticker opens `article_url` for each record. The articles are written
and published by the Elets portal agents (elets-portals, transfers/CXO agent);
this step only finds the published post for each move on the portal's public
WordPress REST API and records it in data/articles.json, which
build_dataset.py re-attaches on every run. Moves without a published article
are kept out of the ticker feed by make_api.py, so the ticker never links to
an outside site.

No credentials: public, published posts only. Run after build_dataset.py.
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from publish_articles import record_id  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "moves_master.json"
STATE = ROOT / "data" / "articles.json"
MISSES = ROOT / "data" / "article_misses.json"
# sector label -> portal that publishes its moves as WordPress posts
PORTALS = {"BFSI": "https://bfsi.eletsonline.com"}
DAYS = 30            # only recent moves can appear in the ticker
RECHECK_HOURS = 3    # how often an unlinked move is looked up again
MAX_LOOKUPS = 150    # per run, keeps the job well inside its time budget
UA = "Mozilla/5.0 (compatible; EletsCXOTracker/1.0)"


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", html.unescape(s or "").lower())


GENERIC = {"bank", "ltd", "limited", "india", "the", "of", "and", "co", "company", "group", "holdings", "insurance", "general",
           "life", "finance", "financial", "small", "services", "securities", "corporation", "corp", "plc", "inc", "amc", "pvt"}


def matches(title, person, company=""):
    """Every word of the name as a whole word, and the company's distinctive words, in the post title."""
    t = set(norm(title).split())
    p = [w for w in norm(person).split() if len(w) > 1]
    c = [w for w in norm(company).split() if w not in GENERIC and len(w) > 1][:2]
    return bool(p) and all(w in t for w in p) and all(w in t for w in c)


def lookup(base, person, company=""):
    q = urllib.parse.urlencode({"search": person, "per_page": 10, "_fields": "link,title,status"})
    req = urllib.request.Request(f"{base}/wp-json/wp/v2/posts?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        rows = json.loads(r.read().decode("utf-8"))
    for row in rows:
        if matches(row.get("title", {}).get("rendered", ""), person, company):
            return row["link"], html.unescape(row["title"]["rendered"])
    return None


def main():
    recs = json.loads(DATA.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    misses = json.loads(MISSES.read_text(encoding="utf-8")) if MISSES.exists() else {}
    now = datetime.now(timezone.utc)
    cutoff = (date.today() - timedelta(days=DAYS)).isoformat()
    found = looked = 0
    for r in recs:
        base = PORTALS.get(r.get("sector"))
        if not base or (r.get("date") or "") < cutoff or not r.get("person"):
            continue
        rid = record_id(r)
        if rid in state:
            continue
        last = misses.get(rid)
        if last and now - datetime.fromisoformat(last) < timedelta(hours=RECHECK_HOURS):
            continue
        if looked >= MAX_LOOKUPS:
            break
        looked += 1
        try:
            hit = lookup(base, r["person"], r.get("company", ""))
        except Exception as e:  # one failed lookup must not stop the feed
            print(f"  lookup failed for {r['person']}: {e}")
            continue
        time.sleep(0.3)
        if hit:
            state[rid] = {"url": hit[0], "site": base, "status": "publish", "title": hit[1],
                          "linked_at": now.isoformat(timespec="seconds")}
            misses.pop(rid, None)
            found += 1
        else:
            misses[rid] = now.isoformat(timespec="seconds")
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    MISSES.write_text(json.dumps(misses, indent=0), encoding="utf-8")
    # re-attach so make_api sees the links in this same run
    by = {rid: v["url"] for rid, v in state.items()}
    for r in recs:
        u = by.get(record_id(r))
        if u:
            r["article_url"] = u
    DATA.write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"linked {found} new portal articles ({looked} looked up, {len(state)} total)")


if __name__ == "__main__":
    main()
