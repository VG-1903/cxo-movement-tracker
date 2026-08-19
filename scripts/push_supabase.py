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
            "company": r.get("company", ""), "sector": r.get("sector", ""),
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
    sent = 0
    for i in range(0, len(rows), BATCH):
        body = json.dumps(rows[i:i + BATCH], ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status not in (200, 201, 204):
                print(f"batch {i}: HTTP {resp.status}")
                sys.exit(1)
        sent += min(BATCH, len(rows) - i)
        print(f"upserted {sent}/{len(rows)}")
    print("supabase sync complete")


if __name__ == "__main__":
    main()
