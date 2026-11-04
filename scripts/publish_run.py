"""Put a graded field run on the console. python scripts/publish_run.py runs/<clip> --id field-tray1 --label "Real fish, tape-checked"
Copies run.json, frame.jpg, overlay.jpg and catch.csv into web/samples/<id>/ and puts {"id","label"} first in
web/samples/index.json (replacing an entry with the same id), so the console opens on the real run by default."""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `python scripts/...` finds the package

ROOT = Path(__file__).resolve().parent.parent
FILES = ["run.json", "frame.jpg", "overlay.jpg", "catch.csv"]


def publish(run_dir: Path, sid: str, label: str, samples: Path = ROOT / "web/samples") -> Path:
    if not re.fullmatch(r"[a-z0-9-]+", sid):
        sys.exit(f"--id must be [a-z0-9-]+, got {sid!r}")
    if not (run_dir / "run.json").exists():
        sys.exit(f"No run.json in {run_dir}: grade the run first")
    out = samples / sid
    out.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copy2(run_dir / name, out / name)
    index = samples / "index.json"
    rest = [e for e in (json.loads(index.read_text()) if index.exists() else []) if e["id"] != sid]
    index.write_text(json.dumps([{"id": sid, "label": label}] + rest))
    print(f"{run_dir} -> {out} ({', '.join(FILES)}); first in {index} as {sid!r} \"{label}\", then {[e['id'] for e in rest]}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--id", required=True)
    ap.add_argument("--label", required=True)
    a = ap.parse_args()
    publish(a.run_dir, a.id, a.label)
