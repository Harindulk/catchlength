"""How much length error do the camera and the tiles add on their own, before any model is involved?
Random synthetic scenes (museum reference fish at known lengths), degraded like a 1080p phone frame from ~1 m,
measured with each fish's true mask. python scripts/geometry_budget.py [n_scenes]"""
import sys

import cv2
import numpy as np

from catchlength.geometry import axis_length_mm
from catchlength.mat import MATS, detect_tiles
from catchlength.synth import make_scene

n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
errs, missed = [], 0
for seed in range(n):
    rng = np.random.default_rng(100 + seed)
    k = int(rng.integers(3, 6))
    lengths = rng.uniform(220, 460, k)
    pos = [(300 + rng.uniform(-20, 20), 80 + 115 * i) for i in range(k)]  # one fish per row: none overlap
    sc = make_scene(lengths, pos, angles=list(rng.uniform(-6, 6, k)), seed=seed, tiles=((620, 20), (640, 400)))
    s = 0.45  # ~0.9 px/mm, like 1080p from about 1 m
    img = cv2.GaussianBlur(cv2.resize(sc.image, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), (0, 0), 0.8)
    img = np.clip(img + rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8)
    img = cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1], 1)
    fixes = detect_tiles(img, MATS["A4"], 4)
    if not fixes:
        missed += 1
        continue
    for m, L in zip(sc.masks, lengths):
        mm = cv2.resize(m.astype(np.uint8), (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
        if mm.sum() < 50:
            continue
        cy, cx = np.argwhere(mm).mean(0)
        best = min(fixes.values(), key=lambda f: np.linalg.norm(
            cv2.perspectiveTransform(np.float32([[[148.5, 105]]]), np.linalg.inv(f.H))[0, 0] - (cx, cy)))
        errs.append(axis_length_mm(mm, best.H)[0] - L)
e = np.array(errs) / 10
a = np.abs(e)
print(f"{len(e)} fish in {n - missed} scenes ({missed} without a tile): mean abs error {a.mean():.2f} cm, "
      f"P90 {np.percentile(a, 90):.2f} cm, bias {e.mean():+.2f} cm, worst {a.max():.2f} cm")
