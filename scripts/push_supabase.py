"""Upsert data/moves_master.json into a Supabase 'moves' table via PostgREST.

Credentials come from .env.local in the project root (gitignored — never commit):
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
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "moves_master.json"
ENV = ROOT / ".env.local"
BATCH = 500


def load_env():
    if not ENV.exists():
        print("no .env.local — skipping Supabase push")
        sys.exit(0)
    env = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    url, key = env.get("SUPABASE_URL"), env.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY missing in .env.local")
        sys.exit(1)
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
    OPTIONAL_COLS = ["moved_from", "moved_from_source"]

    def post(batch):
        body = json.dumps(batch, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status

    sent, dropped = 0, False
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        if dropped:
            batch = [{k: v for k, v in r.items() if k not in OPTIONAL_COLS} for r in batch]
        try:
            post(batch)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            if e.code == 400 and "PGRST204" in detail and not dropped:
                dropped = True
                print(f"table lacks {OPTIONAL_COLS} — syncing without them. "
                      "To store them, run in Supabase SQL Editor:\n"
                      "  alter table public.moves add column if not exists moved_from text,"
                      " add column if not exists moved_from_source text;")
                batch = [{k: v for k, v in r.items() if k not in OPTIONAL_COLS} for r in batch]
                try:
                    post(batch)
                except urllib.error.HTTPError as e2:
                    print(f"batch {i}: HTTP {e2.code} — "
                          f"{e2.read().decode('utf-8', 'replace')[:300]}")
                    sys.exit(1)
            else:
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
    print("supabase sync complete" + (" (WITHOUT moved_from columns)" if dropped else ""))


if __name__ == "__main__":
    main()
