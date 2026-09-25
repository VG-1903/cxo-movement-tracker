"""Upsert data/moves_master.json into a Supabase 'moves' table via PostgREST.

Credentials come from .env.local in the project root (gitignored — never commit),
or from the same-named environment variables when running in CI (repo secrets):
    SUPABASE_URL=https://xxxx.supabase.co
    SUPABASE_SERVICE_KEY=eyJ...   (service_role key — server-side only)

Run scripts/../supabase/schema.sql once in Supabase Studio first.
Consumers then query with the anon key, e.g.:
    GET {SUPABASE_URL}/rest/v1/moves?sector=eq.Pharma%20%26%20Healthcare
        &region=eq.India&order=date.desc&limit=20
    headers: apikey: <anon key>
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "moves_master.json"
ENV = ROOT / ".env.local"
BATCH = 500


def load_env():
    # .env.local locally; real environment variables in CI (repo secrets).
    # Neither present = nothing to sync, which is not an error: the static API
    # is the primary product and must not fail the run over a missing mirror.
    env = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    url = env.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = env.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        where = ".env.local" if ENV.exists() else ".env.local or environment"
        print(f"SUPABASE_URL / SUPABASE_SERVICE_KEY not set in {where} "
              "— skipping Supabase push")
        sys.exit(0)
    return url.rstrip("/"), key


def main():
    url, key = load_env()
    recs = json.loads(DATA.read_text(encoding="utf-8"))
    rows = []
    for r in recs:
        rid = hashlib.sha1(
            f"{r['person']}|{r['company']}|{r['movement']}".lower().encode("utf-8")
        ).hexdigest()
        rows.append({
            "id": rid, "date": r.get("date") or None, "person": r["person"],
            "movement": r["movement"], "role": r.get("role", ""),
            "role_group": r.get("role_group", ""),
            "company": r.get("company", ""),
            "moved_from": r.get("moved_from", ""),
            "moved_from_source": r.get("moved_from_source", ""),
            "sector": r.get("sector", ""),
            "region": r.get("region", ""), "publisher": r.get("publisher", ""),
            "headline": r.get("headline", ""), "link": r.get("link", ""),
            "also_reported_by": r.get("also_reported_by", []),
        })

    endpoint = f"{url}/rest/v1/moves?on_conflict=id"
    headers = {
        "apikey": key, "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    # columns that may not exist yet in older tables; dropped on PGRST204
    OPTIONAL_COLS = ["moved_from", "moved_from_source", "role_group"]

    def post(batch):
        body = json.dumps(batch, ensure_ascii=False).encode("utf-8")
        # connections get dropped mid-upload sometimes (SSLEOFError/URLError);
        # upserts are idempotent, so retry with backoff before giving up
        for attempt in range(4):
            req = urllib.request.Request(endpoint, data=body, headers=headers,
                                         method="POST")
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return resp.status
            except urllib.error.HTTPError:
                raise  # real API error — let the caller inspect it
            except (urllib.error.URLError, OSError) as e:
                if attempt == 3:
                    raise
                print(f"  transient error ({e.reason if hasattr(e, 'reason') else e}) "
                      f"— retry {attempt + 1}/3 in {2 ** attempt * 5}s")
                time.sleep(2 ** attempt * 5)

    # Drop only the optional column(s) the table really lacks. PostgREST names
    # the missing column in PGRST204; dropping all three on any miss emptied
    # moved_from for every row of a table that only lacked role_group.
    sent, dropped = 0, set()
    for i in range(0, len(rows), BATCH):
        while True:
            batch = [{k: v for k, v in r.items() if k not in dropped}
                     for r in rows[i:i + BATCH]]
            try:
                post(batch)
                break
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:500]
                m = re.search(r"'(\w+)' column", detail)
                col = m.group(1) if m else ""
                if e.code == 400 and "PGRST204" in detail and col in OPTIONAL_COLS and col not in dropped:
                    dropped.add(col)
                    print(f"table lacks column '{col}' — syncing without it. To store it, "
                          f"run in Supabase SQL Editor:\n"
                          f"  alter table public.moves add column if not exists {col} text;")
                    continue
                print(f"batch {i}: HTTP {e.code} — {detail}")
                if e.code == 404:
                    print("\nThe 'moves' table does not exist yet. Run supabase/schema.sql "
                          "in Supabase Studio -> SQL Editor first.")
                sys.exit(1)
        sent += len(rows[i:i + BATCH])
        print(f"upserted {sent}/{len(rows)}")

    # remove rows no longer in the master dataset (e.g. collapsed by dedupe)
    local_ids = {r["id"] for r in rows}
    remote_ids, offset = set(), 0
    while True:
        req = urllib.request.Request(
            f"{url}/rest/v1/moves?select=id&limit=1000&offset={offset}",
            headers={"apikey": key, "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            page = json.loads(resp.read().decode("utf-8"))
        remote_ids.update(r["id"] for r in page)
        if len(page) < 1000:
            break
        offset += 1000
    stale = sorted(remote_ids - local_ids)
    for i in range(0, len(stale), 80):
        chunk = ",".join(f'"{s}"' for s in stale[i:i + 80])
        req = urllib.request.Request(
            f"{url}/rest/v1/moves?id=in.({urllib.parse.quote(chunk)})",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Prefer": "return=minimal"},
            method="DELETE")
        urllib.request.urlopen(req, timeout=60).read()
    if stale:
        print(f"deleted {len(stale)} stale rows")
    print("supabase sync complete" + (f" (without column(s): {', '.join(sorted(dropped))})" if dropped else ""))


if __name__ == "__main__":
    main()
