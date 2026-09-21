"""Write an AI news article for each new movement and publish it to WordPress.

Runs after build_dataset.py. For every record that has no article yet (and is
recent enough to still be news) it asks Claude for a short, attributed news
piece, posts it to the WordPress site mapped to the record's sector, and
stamps the resulting URL onto the record as `article_url` — which the
dashboard, API and widget then link to.

State lives in data/articles.json keyed by the record id (sha1 of
person|company|movement, the same id Supabase uses), so rebuilds of
moves_master.json never lose track of what was already published.

Configuration (environment variables, or .env.local locally):
    ANTHROPIC_API_KEY      required to generate articles
    WP_SITES               JSON map of sector -> WordPress base URL, e.g.
                           {"BFSI": "https://bfsi.example.com",
                            "Healthcare": "https://ehealth.example.com",
                            "default": "https://www.example.com"}
                           (a single WP_URL is accepted as the default site)
    WP_USER                WordPress username
    WP_APP_PASSWORD        WordPress *Application Password* for that user
    WP_STATUS              publish | draft            (default: draft)
    ARTICLE_MODEL          Claude model id             (default: claude-opus-5)
    ARTICLE_MAX_PER_RUN    cap on new articles per run (default: 20)
    ARTICLE_MAX_AGE_DAYS   only write up records this recent (default: 3)

Flags:
    --dry-run   generate articles but do not publish; writes previews to
                data/articles_preview/<id>.html for editorial review.

Without an API key or WordPress credentials the script logs why and exits 0,
so the rest of the pipeline is never blocked by this optional step.
"""
import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "moves_master.json"
STATE = ROOT / "data" / "articles.json"
PREVIEW = ROOT / "data" / "articles_preview"
ENV = ROOT / ".env.local"

DEFAULT_MODEL = "claude-opus-5"

SYSTEM_PROMPT = """You are a newsroom writer for an Indian B2B publisher covering leadership changes across banking & finance, healthcare, pharma, education and the wider corporate sector.

You write short, factual news reports about executive appointments, promotions, resignations and retirements. You are given ONE structured record extracted automatically from a public news headline. Write only from that record.

Hard rules — these protect the publisher from printing things that are not known:
- Use ONLY the facts in the record. Do not invent quotes, dates, figures, tenure lengths, prior employers, qualifications, company descriptions, or reasons for the move.
- If a field is empty or unknown, do not guess it; write around it.
- Attribute the news to the reporting outlet(s) named in the record, e.g. "as reported by <publisher>". If several outlets are listed, say the move was reported by multiple outlets.
- Do not editorialise, speculate about strategy, or praise the person.
- It is fine to add one or two sentences of generic, non-fabricated context about what the role typically involves (e.g. what a CFO is responsible for) — never specific claims about this company or person.
- British/Indian English spelling. Neutral, wire-service tone. 180–300 words in the body.

Output format:
- title: a clean news headline, max 90 characters, no clickbait, no trailing punctuation.
- excerpt: one sentence, max 160 characters, summarising the move.
- body_html: 3–5 paragraphs, each wrapped in <p>…</p>. No headings, no lists, no links, no markdown. The final paragraph must be exactly:
  <p><em>This report is based on publicly available news coverage; details are as stated by the cited source(s).</em></p>
- tags: 3–6 short tags (person name, company, role, sector)."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "excerpt": {"type": "string"},
        "body_html": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "excerpt", "body_html", "tags"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- config
def load_env():
    """Merge .env.local (if present) under the real environment."""
    env = dict(os.environ)
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


def site_map(env):
    raw = env.get("WP_SITES", "").strip()
    if raw:
        try:
            sites = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"WP_SITES is not valid JSON: {e}")
            sys.exit(1)
    else:
        sites = {}
    if env.get("WP_URL") and "default" not in sites:
        sites["default"] = env["WP_URL"]
    return {k: v.rstrip("/") for k, v in sites.items()}


def record_id(r):
    return hashlib.sha1(
        f"{r['person']}|{r.get('company', '')}|{r['movement']}".lower().encode("utf-8")
    ).hexdigest()


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:60]


# ---------------------------------------------------------------- generation
def generate_article(client, model, rec):
    outlets = [rec.get("publisher", "")] + list(rec.get("also_reported_by", []))
    outlets = [o for o in outlets if o]
    facts = {
        "person": rec["person"],
        "movement": rec["movement"],
        "role": rec.get("role", ""),
        "company": rec.get("company", ""),
        "previous_employer": rec.get("moved_from", ""),
        "sector": rec.get("sector", ""),
        "region": rec.get("region", ""),
        "date_reported": rec.get("date", ""),
        "headline_as_published": rec.get("headline", ""),
        "reported_by": outlets,
    }
    response = client.messages.create(
        model=model,
        max_tokens=4000,
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
        },
        system=[{"type": "text", "text": SYSTEM_PROMPT,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content":
                   "Write the news report for this record:\n"
                   + json.dumps(facts, ensure_ascii=False, indent=2)}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("model declined to write this record")
    text = next(b.text for b in response.content if b.type == "text")
    art = json.loads(text)
    art["usage"] = {"in": response.usage.input_tokens,
                    "out": response.usage.output_tokens}
    return art


# ---------------------------------------------------------------- wordpress
class WordPress:
    def __init__(self, base, user, app_password):
        self.base = base
        token = base64.b64encode(f"{user}:{app_password}".encode("utf-8")).decode("ascii")
        self.headers = {"Authorization": f"Basic {token}",
                        "Content-Type": "application/json",
                        "User-Agent": "cxo-movement-tracker/1.0"}
        self._cats = {}

    def _req(self, method, path, body=None, query=None):
        url = f"{self.base}/wp-json/wp/v2/{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self.headers, method=method)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8") or "null")

    def find_by_slug(self, slug):
        # status=any needs an authenticated request, which we always send
        posts = self._req("GET", "posts", query={"slug": slug, "status": "any"})
        return posts[0] if posts else None

    def category_id(self, name):
        """Get-or-create a category; None if the user may not create terms."""
        if not name:
            return None
        if name in self._cats:
            return self._cats[name]
        try:
            hits = self._req("GET", "categories", query={"search": name, "per_page": 20})
            for c in hits:
                if c["name"].lower() == name.lower():
                    self._cats[name] = c["id"]
                    return c["id"]
            created = self._req("POST", "categories", {"name": name})
            self._cats[name] = created["id"]
        except urllib.error.HTTPError as e:
            print(f"    category '{name}' unavailable (HTTP {e.code}); posting uncategorised")
            self._cats[name] = None
        return self._cats[name]

    def create_post(self, title, content, excerpt, slug, status, category_id):
        body = {"title": title, "content": content, "excerpt": excerpt,
                "slug": slug, "status": status}
        if category_id:
            body["categories"] = [category_id]
        return self._req("POST", "posts", body)


# ---------------------------------------------------------------- main
def main():
    dry_run = "--dry-run" in sys.argv
    env = load_env()
    api_key = env.get("ANTHROPIC_API_KEY")
    sites = site_map(env)
    wp_user, wp_pass = env.get("WP_USER"), env.get("WP_APP_PASSWORD")
    status = env.get("WP_STATUS", "draft").lower()
    model = env.get("ARTICLE_MODEL", DEFAULT_MODEL)
    max_per_run = int(env.get("ARTICLE_MAX_PER_RUN", "20"))
    max_age = int(env.get("ARTICLE_MAX_AGE_DAYS", "3"))

    if not api_key:
        print("ANTHROPIC_API_KEY not set — skipping article generation")
        return 0
    if not dry_run and not (sites and wp_user and wp_pass):
        print("WP_SITES/WP_URL, WP_USER, WP_APP_PASSWORD not all set — "
              "skipping article publishing (use --dry-run to only generate)")
        return 0
    if status not in ("publish", "draft"):
        print(f"WP_STATUS must be publish or draft, got {status!r}")
        return 1

    import anthropic  # imported late so the skip paths above need no SDK
    client = anthropic.Anthropic(api_key=api_key, max_retries=4)

    recs = json.loads(DATA.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    cutoff = (date.today() - timedelta(days=max_age)).isoformat()

    todo = [r for r in recs
            if record_id(r) not in state and r.get("date", "") >= cutoff]
    todo.sort(key=lambda r: r["date"], reverse=True)
    skipped_no_site = 0
    if not dry_run:
        kept = []
        for r in todo:
            if r["sector"] in sites or "default" in sites:
                kept.append(r)
            else:
                skipped_no_site += 1
        todo = kept
    todo = todo[:max_per_run]
    print(f"articles: {len(state)} already published, {len(todo)} to write this run"
          + (f" ({skipped_no_site} skipped: no WordPress site for their sector)"
             if skipped_no_site else "")
          + (" [DRY RUN]" if dry_run else ""))

    wp_clients = {}
    tokens_in = tokens_out = 0
    written = failed = 0
    if dry_run:
        PREVIEW.mkdir(parents=True, exist_ok=True)

    for r in todo:
        rid = record_id(r)
        label = f"{r['person']} — {r['movement']} — {r.get('company') or '?'}"
        try:
            art = generate_article(client, model, r)
        except anthropic.APIStatusError as e:
            print(f"  FAIL generate [{label}]: HTTP {e.status_code} {e.message}")
            failed += 1
            continue
        except (anthropic.APIConnectionError, RuntimeError, json.JSONDecodeError) as e:
            print(f"  FAIL generate [{label}]: {e}")
            failed += 1
            continue
        tokens_in += art["usage"]["in"]
        tokens_out += art["usage"]["out"]

        slug = f"{slugify(r['person'])}-{slugify(r.get('company') or r['movement'])}-{rid[:8]}"
        if dry_run:
            (PREVIEW / f"{rid}.html").write_text(
                f"<h1>{art['title']}</h1>\n<p><b>{art['excerpt']}</b></p>\n{art['body_html']}\n"
                f"<!-- tags: {', '.join(art['tags'])} -->\n", encoding="utf-8")
            print(f"  preview [{label}] -> data/articles_preview/{rid}.html")
            written += 1
            continue

        base = sites.get(r["sector"]) or sites["default"]
        wp = wp_clients.get(base)
        if wp is None:
            wp = wp_clients[base] = WordPress(base, wp_user, wp_pass)
        try:
            # a previous run may have posted but failed to commit its state
            post = wp.find_by_slug(slug) or wp.create_post(
                art["title"], art["body_html"], art["excerpt"], slug, status,
                wp.category_id(r["sector"]))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200]
            print(f"  FAIL publish [{label}]: HTTP {e.code} {detail}")
            if e.code in (401, 403):
                print("  WordPress rejected the credentials — stopping this run")
                break
            failed += 1
            continue
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  FAIL publish [{label}]: {e}")
            failed += 1
            continue

        state[rid] = {
            "url": post["link"], "post_id": post["id"], "site": base,
            "status": post.get("status", status), "title": art["title"],
            "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        r["article_url"] = post["link"]
        written += 1
        print(f"  {post.get('status', status)} [{label}] -> {post['link']}")

    if not dry_run and written:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        # stamp URLs onto the current dataset so this run's dashboard/API link them
        by_id = {rid: s["url"] for rid, s in state.items()}
        for r in recs:
            u = by_id.get(record_id(r))
            if u:
                r["article_url"] = u
        DATA.write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")

    # Opus 5 list price: $5 / $25 per million tokens
    cost = tokens_in * 5 / 1e6 + tokens_out * 25 / 1e6
    print(f"articles: {written} written, {failed} failed, "
          f"{tokens_in + tokens_out} tokens (~${cost:.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
