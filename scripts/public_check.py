"""Stress test on public footage, before field use: python scripts/public_check.py
Frames from FWC's "How to Measure a Fish" (CC BY, youtu.be/2Va-ANxdQhM): real wet fish on a measuring board, at an
angle, partly under hands, and no marker tiles. Three questions, none of them length (no tiles, no tape truth):
1. does the whole agent refuse to measure without tiles; 2. does SAM 3.1 find each fish; 3. what does Spark call a
Spanish mackerel and a black sea bass, neither on its five-species list (right answer: "unknown").
Clips stay in data/raw/public/ (git-ignored); only results and the link are kept."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from catchlength import agent, sam, spark
from catchlength.api import Client

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/raw/public/fwc"
# frame -> fish a person counts in it (by eye, from the contact sheet)
FRAMES = {"t50": 2, "t56": 2, "t80": 1, "t86": 1}

out = {"source": "FWC Saltwater Fishing, 'How to Measure a Fish', CC BY, https://youtu.be/2Va-ANxdQhM",
       "frames": {}}
client = Client(1.00)
for name, truth in FRAMES.items():
    img = cv2.imread(str(SRC / f"{name}.jpg"))
    h, w = img.shape[:2]
    res = client.call("responses", sam.request(img, "fish"), sam.USD_PER_IMAGE)
    dets = sam.parse(res.get("output_text") or agent._output_text(res), (w, h))
    fish = []
    for d in dets:
        l, t, r, b = map(int, d.box)
        crop = img[max(0, t - 20):b + 20, max(0, l - 20):r + 20]
        sp = spark.species(client, crop)
        fish.append({"box": [l, t, r, b], "sam_conf": d.confidence, "species": sp["species"], "species_conf": sp["confidence"]})
        cv2.rectangle(img, (l, t), (r, b), (255, 120, 0), 3)
        cv2.putText(img, f"{sp['species']} {sp['confidence']:.2f}", (l, max(24, t - 8)), cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 120, 0), 2)
    run = agent.run_agent(agent.Run([cv2.imread(str(SRC / f"{name}.jpg"))], client, f"public: FWC {name}"), max_turns=10)
    out["frames"][name] = {"fish_by_eye": truth, "sam_found": len(dets), "fish": fish, "agent_status": run.status,
                           "agent_lengths_filed": sum(f.status == "measured" for f in run.fish.values()),
                           "agent_tools": [l["tool"] for l in run.log], "reviews": [r["reason"][:160] for r in run.reviews]}
    cv2.imwrite(str(SRC / f"{name}_checked.jpg"), img)
    print(name, out["frames"][name]["sam_found"], "/", truth, [(f["species"], f["species_conf"]) for f in fish], run.status)
out["cost_usd"] = round(client.spent, 4)
(ROOT / "data/public_check.json").write_text(json.dumps(out, indent=1))
print(f"${client.spent:.3f} -> data/public_check.json")
