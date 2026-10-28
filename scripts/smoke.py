"""First contact with the real models, for a few cents: one Muse Spark ping, then SAM 3.1 and Spark on a
synthetic scene of museum fish at known lengths. python scripts/smoke.py
Prints what came back and what it cost; responses are cached, so a rerun is free."""
import json
import time

import cv2
import numpy as np

from catchlength import sam, spark
from catchlength.api import Client
from catchlength.geometry import axis_length_mm
from catchlength.mat import MATS, detect_tiles
from catchlength.synth import make_scene

c = Client(budget_usd=0.50)
t = time.time()
r = c.call("chat", {"model": spark.MODEL, "messages": [{"role": "user", "content": "Reply with the single word: ready"}]}, 0.001)
print("spark ping:", r["choices"][0]["message"]["content"].strip(), f"({time.time() - t:.1f}s)")

lengths = [420, 380, 300, 250, 330]
scene = make_scene(lengths, [(400, 130), (450, 330), (820, 140), (250, 520), (470, 545)], angles=[5, -10, 8, 0, 0], seed=1)
plan = spark.plan(c, [scene.image])
print("spark plan:", json.dumps(plan))

out = c.call("responses", sam.request(scene.image, "fish"), sam.USD_PER_IMAGE)
text = out.get("output_text") or "".join(x.get("text", "") for o in out.get("output", []) for x in (o.get("content") or []))
dets = sam.parse(text, (scene.image.shape[1], scene.image.shape[0]))
fixes = detect_tiles(scene.image, MATS["A4"], 4)
H = next(iter(fixes.values())).H
print(f"sam found {len(dets)} fish (5 placed); confidences {[d.confidence for d in dets]}")
for d in dets:  # match each detection to the pasted fish it overlaps most
    k = int(np.argmax([np.logical_and(d.mask, m).sum() for m in scene.masks]))
    print(f"  fish {d.id}: outline {axis_length_mm(d.mask, H)[0] / 10:.1f} cm vs pasted {lengths[k] / 10:.1f} cm")
if dets:
    l, tp, rr, b = map(int, dets[0].box)
    kp = spark.keypoints(c, scene.image[max(0, tp - 20):b + 20, max(0, l - 20):rr + 20])
    sp = spark.species(c, scene.image[max(0, tp - 20):b + 20, max(0, l - 20):rr + 20])
    print("spark points:", kp, "\nspark species:", sp)
print(f"spent ${c.spent:.4f} over {len(c.ledger)} calls")
