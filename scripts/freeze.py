"""Freeze the code and thresholds before field data exists: python scripts/freeze.py [--name freeze-2026-11-01]
Refuses on uncommitted changes or failing tests, then makes an annotated git tag (local only, never pushed here)
whose message lists every threshold, the kill test and the held-out fish. Every receipt then prints the tag and
whether catchlength/, config/ and data/rules.json still match it (catchlength.cli.code_version)."""
import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from catchlength.agent import THRESHOLDS, TL_FROM_FL  # noqa: E402
from catchlength.audit import HELD_OUT, KILL  # noqa: E402


def git(*a: str, check: bool = True) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=check).stdout.strip()


def message(name: str) -> str:
    return "\n".join([
        f"{name}: code and thresholds frozen before the field shoot.", "",
        "thresholds: " + json.dumps(THRESHOLDS),
        "species TL-from-FL (TL = a*FL + b, cm): " + json.dumps({k: v for k, v in TL_FROM_FL.items() if v}),
        "kill test: " + json.dumps(KILL),
        "held-out bias split: tags " + ", ".join(sorted(HELD_OUT, key=int)) +
        " (bias fitted on the other fish, scored on these)"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default=f"freeze-{date.today().isoformat()}")
    a = ap.parse_args()
    if not a.name.startswith("freeze-"):
        sys.exit("Tag names start with freeze- (receipts look for that prefix)")
    if git("tag", "--list", a.name):
        sys.exit(f"{a.name} already exists at {git('rev-list', '-n1', '--abbrev-commit', a.name)}; pick another --name")
    if git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("Commit or stash the tracked changes first: a freeze must point at a commit")
    if subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True).returncode:
        sys.exit("Tests fail: fix them before freezing (run .venv/bin/python -m pytest -q)")
    git("tag", "-a", a.name, "-m", message(a.name))
    print(f"Frozen: {a.name} at {git('rev-parse', '--short', 'HEAD')} (local tag; push it only with the repo)")


if __name__ == "__main__":
    main()
