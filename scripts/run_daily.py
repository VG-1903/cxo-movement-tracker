"""Daily pipeline: fetch -> build dataset -> regenerate dashboard. Logs to data/logs/."""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "data" / "logs"
PY = sys.executable


def git_push(f):
    """Commit & push refreshed data so GitHub Pages serves the update."""
    # under Task Scheduler there is no terminal: fail fast instead of git
    # trying (and dying) to prompt for credentials
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    trace = LOGS / "git_push_trace.log"

    def run(*args, traced=False):
        e = env
        if traced:
            # git-level trace shows which credential helper git actually ran
            # (for github.com that is `gh auth git-credential`, not GCM — a
            # logged-out gh broke every push 2026-09-03..14). Overwritten each
            # run; only consulted when the push fails.
            trace.unlink(missing_ok=True)
            e = {**env, "GIT_TRACE": str(trace)}
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, env=e,
                           text=True, encoding="utf-8", errors="replace", timeout=300)
        f.write((r.stdout or "") + (r.stderr or ""))
        return r.returncode
    run("add", "-A")
    if run("commit", "-m", f"daily update {datetime.now():%Y-%m-%d}") == 0:
        if run("push", traced=True) != 0:
            f.write("git push FAILED — will retry on next run. Check "
                    "git_push_trace.log for the credential helper involved; "
                    "if it shows gh.exe, run `gh auth status` / `gh auth login`.\n")
    else:
        f.write("nothing new to commit\n")


def main():
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / f"run_{datetime.now():%Y%m%d}.log"
    # core steps abort the run; optional ones (Supabase mirror) only log —
    # a flaky Supabase connection must not block committing & publishing the site
    steps = [("fetch_news.py", True), ("build_dataset.py", True),
             ("publish_articles.py", False),  # AI write-ups; no-ops without keys
             ("make_dashboard.py", True), ("make_api.py", True),
             ("push_supabase.py", False)]  # supabase step no-ops until .env.local exists
    failed_optional = []
    with log.open("a", encoding="utf-8") as f:
        f.write(f"\n===== run started {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
        for step, required in steps:
            f.write(f"--- {step} ---\n")
            f.flush()
            r = subprocess.run([PY, str(ROOT / "scripts" / step)],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=900)
            f.write(r.stdout or "")
            if r.stderr:
                f.write("[stderr]\n" + r.stderr)
            if r.returncode != 0:
                if required:
                    f.write(f"FAILED (exit {r.returncode}) — aborting run\n")
                    sys.exit(r.returncode)
                failed_optional.append(step)
                f.write(f"FAILED (exit {r.returncode}) — optional step, continuing\n")
        f.write("--- git push ---\n")
        git_push(f)
        f.write(f"===== run finished {datetime.now():%Y-%m-%d %H:%M:%S}"
                + (f" (optional failures: {', '.join(failed_optional)})" if failed_optional else "")
                + " =====\n")
    sys.exit(2 if failed_optional else 0)


if __name__ == "__main__":
    main()
