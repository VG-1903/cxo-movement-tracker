"""Daily pipeline: fetch -> build dataset -> regenerate dashboard. Logs to data/logs/."""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "data" / "logs"
PY = sys.executable


def git_push(f):
    """Commit & push refreshed data so GitHub Pages serves the update."""
    def run(*args):
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=300)
        f.write((r.stdout or "") + (r.stderr or ""))
        return r.returncode
    run("add", "-A")
    if run("commit", "-m", f"daily update {datetime.now():%Y-%m-%d}") == 0:
        if run("push") != 0:
            f.write("git push FAILED — will retry on next run\n")
    else:
        f.write("nothing new to commit\n")


def main():
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / f"run_{datetime.now():%Y%m%d}.log"
    steps = ["fetch_news.py", "build_dataset.py", "make_dashboard.py", "make_api.py",
             "push_supabase.py"]  # supabase step no-ops until .env.local exists
    with log.open("a", encoding="utf-8") as f:
        f.write(f"\n===== run started {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
        for step in steps:
            f.write(f"--- {step} ---\n")
            f.flush()
            r = subprocess.run([PY, str(ROOT / "scripts" / step)],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=900)
            f.write(r.stdout or "")
            if r.stderr:
                f.write("[stderr]\n" + r.stderr)
            if r.returncode != 0:
                f.write(f"FAILED (exit {r.returncode}) — aborting run\n")
                sys.exit(r.returncode)
        f.write("--- git push ---\n")
        git_push(f)
        f.write(f"===== run finished {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")


if __name__ == "__main__":
    main()
