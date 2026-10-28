"""Sunday in one command. python scripts/field_day.py data/raw/2026-11-01
1. Runs the agent on every clip in the folder (cached, so re-running is free) -> runs/<clip>/.
2. For each run without tags.json, writes a tags.json stub listing its fish ids: fill each with "<batch>-<tag>"
   by looking at runs/<clip>/overlay.jpg (the masking-tape number beside each head), and set "batch".
3. When every run has tags filled in, grades them against ground_truth.csv -> web/benchmark.json."""
import json
import sys
from pathlib import Path

from catchlength.agent import Run, run_agent
from catchlength.api import Client
from catchlength.audit import grade
from catchlength.cli import load_frames, save

day = Path(sys.argv[1])
clips = sorted(p for p in day.iterdir() if p.suffix.lower() in {".mp4", ".mov", ".jpg", ".jpeg"})
runs = []
for clip in clips:
    out = Path("runs") / clip.stem
    if not (out / "run.json").exists():
        run = run_agent(Run(load_frames(str(clip), 6), Client(0.60), clip.name))
        save(run, out, str(clip))
        print(f"{clip.name}: {run.status}, {len(run.fish)} fish, ${run.client.spent:.3f}")
    tags = out / "tags.json"
    if not tags.exists():
        fish = [f["id"] for f in json.loads((out / "run.json").read_text())["fish"]]
        tags.write_text(json.dumps({"batch": "", "tags": {f: "" for f in fish}}, indent=1))
        print(f"  label {out}/overlay.jpg -> {tags}")
    runs.append(out)

meta = [json.loads((r / "tags.json").read_text()) for r in runs]
todo = [str(r) for r, m in zip(runs, meta) if not m["batch"] or not all(m["tags"].values())]
if todo:
    sys.exit(f"Tag these runs first: {', '.join(todo)}")
import csv  # noqa: E402
gt = list(csv.DictReader(open(day / "ground_truth.csv")))
res = grade(gt, [{"source": json.loads((r / "run.json").read_text())["source"], "batch": m["batch"],
                  "tags": m["tags"], "fish": json.loads((r / "run.json").read_text())["fish"]} for r, m in zip(runs, meta)])
Path("web/benchmark.json").write_text(json.dumps(res, indent=1))
L = res["length_accepted_only"]
print(f"{res['n_measured']} fish: MAE {L['mae']} cm on accepted, within 2 cm {L.get('within_2cm')}, "
      f"count exact {res['count']['exact_rate']}, species {res['species']['accuracy']}, pass marks {res['pass_marks']}")
