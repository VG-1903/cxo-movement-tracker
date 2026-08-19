# CEO / CXO Transfer Portal

Tracks **who is moving where** at the leadership level — appointments, promotions,
re-appointments, resignations and retirements — across **BFSI**, **Education**,
**Pharma & Healthcare** and general **Corporate** (big-company CEOs/CXOs).
Built on the same architecture as the IAS/Speakers portal: `scripts → data → output`,
with a self-contained HTML dashboard.

## 📊 Open this first
- **`output/CXO_Moves_Dashboard.html`** — double-click to open (self-contained, no internet).
  Search, sector & movement-type chips, India/Global toggle, date ranges, charts,
  sortable table with source links, **Export filtered CSV**. Light & dark mode.
- **`output/moves.csv`** — the full dataset for Excel.

## How it works (updates itself daily)
1. **Fetch** (`scripts/fetch_news.py`) — pulls ~35 feeds defined in `sources.json`:
   - **Google News RSS** with 23 targeted boolean queries per sector (the backbone —
     appointments, exits, promotions, RBI/IRDAI/SEBI approvals, VC appointments,
     named big-company lists for banks/insurers/NBFCs/pharma/hospitals/edtech, PSUs,
     role-specific CHRO/CTO/CIO/CFO queries).
   - **Publisher RSS**: ET verticals (ETBFSI, ETHealthworld, ETPharma, ETEducation,
     ETHRWorld), HR Katha, Express Pharma/Healthcare, Business Standard Companies,
     Higher Education Digest, Moneycontrol, MediaNews4u — filtered to people headlines.
   `--backfill` sweeps the last **12 months month-by-month** (Google News
   `after:`/`before:` operators sidestep the 100-item-per-query cap); fetches run
   8-way threaded.
   New headlines accumulate in `data/raw/items.jsonl` (deduped by title).
2. **Parse** (`scripts/parser_lib.py` + `build_dataset.py`) — ~20 regex patterns turn
   each headline into `person · role · company · movement type`, canonicalise roles
   (MD & CEO, CFO, Vice Chancellor…), classify **sector** and **region (India/Global)**,
   and dedupe the same story across outlets (extra outlets recorded in
   `also_reported_by`). Master dataset: `data/moves_master.json`.
3. **Render** (`scripts/make_dashboard.py`) — regenerates the dashboard from the
   template in `scripts/dashboard_template.html`.

## Deployment & API
- **Live site**: https://cxo-movement-tracker.vercel.app (Vercel, auto-deploys on every push)
- **Static JSON API**: `api/v1/{all,bfsi,pharma,education,corporate}.json` (+ `*_latest.json`),
  CORS-open, regenerated daily by `scripts/make_api.py`.
- **Queryable API**: Supabase `moves` table (project `ovcjcdzabuavspbqiqbr`), synced daily by
  `scripts/push_supabase.py`. Read-only for the publishable key via row-level security;
  supports server-side filters, sorting and pagination (PostgREST syntax).
- **Widget**: `embed.js` — one script tag, `data-sector` / `data-limit` / `data-region` / `data-theme`.
- **Credentials** live in `.env.local` (gitignored, excluded from Vercel). Schema: `supabase/schema.sql`.

## Daily automation
A Windows Task Scheduler job **"CXO Portal Daily Update"** runs the whole pipeline
every day at **08:30** (`scripts/run_daily.py`, logs in `data/logs/`). Manage it:
```bash
schtasks /Query /TN "CXO Portal Daily Update" /V /FO LIST
```
```bash
schtasks /Run /TN "CXO Portal Daily Update"
```
```bash
schtasks /Delete /TN "CXO Portal Daily Update" /F
```

## Manual rebuild
```bash
python scripts/run_daily.py
```
Or step by step: `fetch_news.py` (add `--backfill` for the widest window) →
`build_dataset.py` → `make_dashboard.py`.

## Adding / tuning sources
Edit `sources.json`. `type: "gnews"` entries take a Google News search query
(boolean OR/quotes supported); `type: "rss"` entries take a feed URL, with
`filter_people: true` to keep only movement-ish headlines. New queries merge in on
the next run — dedupe is automatic.

## Honest caveats
- Records are **parsed automatically from headlines** — names/companies are as the
  headline stated them. Always verify via the source link before publishing.
- ~55–60% of fetched headlines are intentionally dropped (court cases, analyses,
  multi-person board lists, headlines that name no person).
- Backfill covers roughly the last 12 months; coverage deepens daily from here as
  the store accumulates.
- Requires `defusedxml` (installed for the system Python 3.11 the scheduler uses).
