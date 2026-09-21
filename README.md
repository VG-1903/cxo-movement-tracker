# CEO / CXO Transfer Portal

Tracks **who is moving where** at the leadership level — appointments, promotions,
re-appointments, resignations and retirements — across **BFSI**, **Education**,
**Pharma**, **Healthcare** and general **Corporate** (big-company CEOs/CXOs).
Built on the same architecture as the IAS/Speakers portal: `scripts → data → output`,
with a self-contained HTML dashboard.

## 📊 Open this first
- **`output/CXO_Moves_Dashboard.html`** — double-click to open (self-contained, no internet).
  Search, sector & movement-type chips, **role filter (CEO / CMO / CDO / CFO / CHRO…)**,
  India/Global toggle, date ranges, charts,
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
   (MD & CEO, CFO, Vice Chancellor…), bucket each into a **role group**
   (`role_group`: CEO · MD · CFO · COO · CMO · CHRO · CTO · CIO · CDO · CISO ·
   Other C-suite · Chairman · Academic Leadership · Board & Directors ·
   Business Heads · President — first match wins, so "MD & CEO" is a CEO move),
   classify **sector** and **region (India/Global)**,
   and dedupe the same story across outlets (extra outlets recorded in
   `also_reported_by`). Master dataset: `data/moves_master.json`.
3. **Write & publish** (`scripts/publish_articles.py`) — for every new movement,
   Claude writes a short attributed news report from the record (facts only, no
   invented quotes/figures, closing disclaimer) and posts it to the WordPress
   site mapped to that sector. The post URL is stored in `data/articles.json`
   (keyed by record id, so rebuilds keep it) and surfaced as `article_url` on
   the dashboard (person name links to it), the API and the widget. Needs
   `ANTHROPIC_API_KEY` + `WP_SITES`/`WP_USER`/`WP_APP_PASSWORD`; without them the
   step logs and skips. `WP_STATUS=draft` (default) lets an editor review before
   going live; `publish` goes straight out. `--dry-run` writes previews to
   `data/articles_preview/` instead of posting. Cost ≈ $0.02 per article.
4. **Render** (`scripts/make_dashboard.py`) — regenerates the dashboard from the
   template in `scripts/dashboard_template.html`.

## Deployment & API
- **Live site**: https://cxo-movement-tracker.vercel.app (Vercel, auto-deploys on every push)
- **Static JSON API**: `api/v1/{all,bfsi,pharma,healthcare,education,corporate}.json` (+ `*_latest.json`),
  CORS-open, regenerated daily by `scripts/make_api.py`. Corporate is additionally
  split by role — `api/v1/corporate_{ceo,md,cfo,coo,cmo,chro,cto,cio,cdo,ciso,csuite,
  chairman,board,head,president}.json` (+ `*_latest.json`); per-role counts live in
  `index.json → corporate_by_role`. Every record everywhere carries `role_group`,
  so the other sectors can be sliced the same way.
- **Queryable API**: Supabase `moves` table (project `ovcjcdzabuavspbqiqbr`), synced daily by
  `scripts/push_supabase.py`. Read-only for the publishable key via row-level security;
  supports server-side filters, sorting and pagination (PostgREST syntax).
- **Widget**: `embed.js` — one script tag, `data-sector` / `data-role` / `data-limit` /
  `data-region` / `data-theme`.
- **Credentials** live in `.env.local` (gitignored, excluded from Vercel). Schema: `supabase/schema.sql`.

## Automation
**Primary: GitHub Actions** — `.github/workflows/update-data.yml` runs the whole
pipeline on GitHub's servers **every 2 hours** and commits the result, which Vercel
deploys. Nothing on the office PC is involved: the push uses the per-run
`GITHUB_TOKEN`, so there is no credential to expire. Secrets (Settings → Secrets →
Actions): `ANTHROPIC_API_KEY`, `WP_SITES`, `WP_USER`, `WP_APP_PASSWORD`,
`SUPABASE_URL`, `SUPABASE_SERVICE_KEY` — every step that needs one skips itself
when it is missing. Variables: `WP_STATUS`, `ARTICLE_MAX_PER_RUN`. Status and manual
runs: https://github.com/VG-1903/cxo-movement-tracker/actions.

**Legacy: Windows Task Scheduler** — the job **"CXO Portal Daily Update"** ran the
same pipeline daily at **08:30** from this PC (`scripts/run_daily.py`, logs in
`data/logs/`); it is disabled now that the cloud run is the single writer, because
two writers race on `main`. Manage it:
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
