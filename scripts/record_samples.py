"""Record the console's samples on the real models (Muse Spark 1.3 + SAM 3.1): three synthetic scenes of museum fish
(Smithsonian USNM, public domain) pasted at known lengths, so every length can be checked against the truth.
  python scripts/record_samples.py          live; needs MODEL_API_KEY in .env, about $0.60 a scene at most
  python scripts/record_samples.py --dry    scripted model stand-ins, free: checks the plumbing only
Writes data/samples/<id>/frames/0.jpg (for live runs on the server) and web/samples/<id>/ (the recorded run)."""
import json
import sys
import tempfile
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `python scripts/...` finds the package
import catchlength.api as api
from catchlength import agent
from catchlength.cli import save
from catchlength.synth import make_scene, scripted_client

ROOT = Path(__file__).resolve().parent.parent
DRY = "--dry" in sys.argv
LENGTHS = [420, 380, 300, 250, 330]
SCENES = [  # id, label, scene kwargs, what the scene tests
    ("museum", "Five fish, two tiles",
     dict(positions_mm=[(400, 130), (450, 330), (820, 140), (250, 520), (470, 545)], angles=[5, -10, 8, 0, 0], seed=1),
     "Five fish apart, two tiles: plan, calibrate, segment, measure, species, rules."),
    ("touching", "Fish touching",
     dict(positions_mm=[(540, 140), (510, 232), (850, 300), (240, 520), (450, 522)], angles=[2, -2, 6, 0, 1], seed=2),
     "Fish laid touching: SAM may merge them, so the count check and box-prompt rescue have to split them."),
    ("no-tile", "No marker tile",
     dict(positions_mm=[(400, 130), (450, 330), (820, 140), (250, 520), (470, 545)], angles=[5, -10, 8, 0, 0], seed=1, tiles=()),
     "No marker tile in view: no scale, so calibration must refuse and the job goes to the officer, no lengths."),
]

if DRY:
    api.CACHE = Path(tempfile.mkdtemp())  # the dry run never touches the real cache
index = []
for sid, label, kw, tests in SCENES:
    scene = make_scene(LENGTHS, **kw)
    frames = ROOT / "data/samples" / sid / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(frames / "0.jpg"), scene.image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    client = scripted_client(scene, setattr) if DRY else api.Client(0.60)
    run = agent.run_agent(agent.Run([scene.image], client, f"synthetic scene: {label.lower()}"))
    out = ROOT / "web/samples" / (sid + "-dry" if DRY else sid)
    save(run, out)
    d = json.loads((out / "run.json").read_text())
    d["synthetic"] = {"note": "Synthetic scene: museum reference fish (Smithsonian USNM, public domain) pasted at known "
                              "lengths." + (" Scripted model stand-ins (dry run)." if DRY else " Real Muse Spark 1.3 and SAM 3.1 calls."),
                      "tests": tests, "true_total_length_cm": [x / 10 for x in LENGTHS], "species": scene.species}
    (out / "run.json").write_text(json.dumps(d, indent=1))
    index.append({"id": out.name, "label": label})
    print(f"{sid}: {run.status}, {len(run.fish)} fish, ${client.spent:.3f} -> {out}")

if not DRY:  # recorded real runs first; the scripted sample stays last, labelled
    (ROOT / "web/samples/index.json").write_text(json.dumps(index + [{"id": "simulated", "label": "Scripted stand-in"}]))
