"""Fetch all configured feeds and accumulate unseen items into data/raw/items.jsonl.

Usage:
    python scripts/fetch_news.py             # daily window (when:3d on Google News)
    python scripts/fetch_news.py --backfill  # sweep the last 12 months, month by month
                                             # (after:/before: sidesteps the 100-item cap)
"""
import json
import sys
import hashlib
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parsedate_to_datetime
from pathlib import Path
from datetime import datetime, timezone

import defusedxml.ElementTree as ET

BACKFILL_MONTHS = 12
WORKERS = 8

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# ET-vertical topstories carry mostly non-people news; keep only movement-ish headlines
PEOPLE_WORDS = (
    "appoint", "named as", "names ", "steps down", "resign", "elevat", "promot",
    "takes charge", "take charge", "takes over as", "joins as", "joins ", "new ceo",
    "new cfo", "new md", "new chief", "re-appoint", "reappoint", "quits", "retires",
    "succeed", "at the helm", "top deck", "leadership change",
)


def fetch_xml(url):
    req = urllib.request.Request(url, headers=UA)
    raw = urllib.request.urlopen(req, timeout=30).read()
    return ET.fromstring(raw)


def parse_items(root, feed_name, sector, filter_people=False):
    out = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        if filter_people and not any(w in title.lower() for w in PEOPLE_WORDS):
            continue
        link = (item.findtext("link") or "").strip()
        publisher = (item.findtext("source") or "").strip()
        # Google News titles end with " - Publisher"
        if not publisher and " - " in title:
            publisher = title.rsplit(" - ", 1)[-1].strip()
        pub = item.findtext("pubDate") or ""
        try:
            date = parsedate_to_datetime(pub).astimezone(timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            date = ""
        out.append({
            "title": title, "link": link, "date": date,
            "publisher": publisher, "feed": feed_name, "sector_hint": sector,
        })
    return out


def title_key(title):
    # strip the " - Publisher" suffix so the same story from two queries dedupes
    base = title.rsplit(" - ", 1)[0] if " - " in title else title
    return hashlib.sha1(base.lower().strip().encode("utf-8")).hexdigest()


def month_slices(n):
    """Last n calendar-month (start, end) date strings, oldest first."""
    today = datetime.now(timezone.utc).date()
    firsts = []
    y, m = today.year, today.month
    for _ in range(n + 1):
        firsts.append(f"{y:04d}-{m:02d}-01")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    firsts.reverse()
    return list(zip(firsts[:-1], firsts[1:]))


def build_jobs(cfg, backfill):
    jobs = []  # (feed, url)
    for feed in cfg["feeds"]:
        if feed["type"] == "gnews":
            if backfill:
                for start, end in month_slices(BACKFILL_MONTHS):
                    q = f"{feed['query']} after:{start} before:{end}"
                    jobs.append((feed, cfg["gnews_base"].format(query=urllib.parse.quote(q))))
                # plus the un-sliced query for the freshest items
                jobs.append((feed, cfg["gnews_base"].format(query=urllib.parse.quote(feed["query"]))))
            else:
                q = feed["query"] + " when:3d"
                jobs.append((feed, cfg["gnews_base"].format(query=urllib.parse.quote(q))))
        else:
            jobs.append((feed, feed["url"]))
    return jobs


def fetch_job(feed, url):
    root = fetch_xml(url)
    return parse_items(root, feed["name"], feed["sector"], feed.get("filter_people", False))


def main():
    backfill = "--backfill" in sys.argv
    cfg = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    RAW.mkdir(parents=True, exist_ok=True)
    store = RAW / "items.jsonl"

    seen = set()
    if store.exists():
        for line in store.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(json.loads(line)["key"])
            except Exception:
                pass

    jobs = build_jobs(cfg, backfill)
    per_feed, failures, new_items = {}, [], []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(fetch_job, feed, url): feed for feed, url in jobs}
        for fut in as_completed(futs):
            feed = futs[fut]
            try:
                items = fut.result()
            except Exception as e:
                failures.append(f"{feed['name']}: {type(e).__name__} {str(e)[:80]}")
                continue
            stats = per_feed.setdefault(feed["name"], [0, 0])
            stats[0] += len(items)
            for it in items:
                k = title_key(it["title"])
                if k in seen:
                    continue
                seen.add(k)
                it["key"] = k
                it["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                new_items.append(it)
                stats[1] += 1

    for name, (pulled, fresh) in sorted(per_feed.items()):
        print(f"{name:26s} pulled={pulled:4d} new={fresh}")

    if new_items:
        with store.open("a", encoding="utf-8") as f:
            for it in new_items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"\nTotal new items: {len(new_items)}  (store: {store})")
    if failures:
        print("Failures:")
        for f_ in failures:
            print("  " + f_)
    # non-zero only if everything failed — partial fetch is still a good day
    if failures and not new_items and len(failures) == len(jobs):
        sys.exit(1)


if __name__ == "__main__":
    main()
