"""A SIMULATED sample for building the console before field data exists: museum reference images (public domain,
pre-hackathon) at known lengths, with a scripted stand-in for Muse Spark and SAM 3.1. Clearly labelled; replaced by
real field runs. python scripts/simulate_run.py web/samples/simulated"""
import json
import sys
import tempfile
from pathlib import Path

import catchlength.api as api
from catchlength import agent
from catchlength.cli import save
from catchlength.synth import make_scene, scripted_client

out = Path(sys.argv[1] if len(sys.argv) > 1 else "web/samples/simulated")
api.CACHE = Path(tempfile.mkdtemp())
lengths, pos = [420, 380, 300, 250, 330], [(400, 130), (450, 330), (820, 140), (250, 520), (470, 545)]
scene = make_scene(lengths, pos, angles=[5, -10, 8, 0, 0], seed=1)
run = agent.run_agent(agent.Run([scene.image] * 3, scripted_client(scene, setattr), "simulated: museum reference fish"))
save(run, out)
d = json.loads((out / "run.json").read_text())
d["simulated"] = {"note": "Simulated run: museum reference images (Smithsonian USNM, public domain) pasted at known lengths, "
                          "with scripted stand-ins for Muse Spark and SAM 3.1. Not a field result.",
                  "true_total_length_cm": [x / 10 for x in lengths], "species": scene.species}
(out / "run.json").write_text(json.dumps(d, indent=1))
print(run.status, len(run.fish), "fish ->", out)
