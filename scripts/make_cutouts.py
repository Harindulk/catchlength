"""Cut the fish out of the public-domain specimen photos (light grey backgrounds) with GrabCut.
Writes data/cutouts/<name>.png (RGBA) used by the synthetic benchmark."""
import glob, os, sys
import cv2
import numpy as np

SRC = sys.argv[1] if len(sys.argv) > 1 else "data/sources"
OUT = sys.argv[2] if len(sys.argv) > 2 else "data/cutouts"
os.makedirs(OUT, exist_ok=True)

for f in sorted(glob.glob(f"{SRC}/*.jpg")):
    im = cv2.imread(f)
    h, w = im.shape[:2]
    lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.float32)
    border = np.concatenate([lab[:10].reshape(-1, 3), lab[-10:].reshape(-1, 3), lab[:, :10].reshape(-1, 3), lab[:, -10:].reshape(-1, 3)])
    dist = np.linalg.norm(lab - np.median(border, 0), axis=2)
    rough = (dist > 18).astype(np.uint8)
    rough = cv2.morphologyEx(rough, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(rough)
    big = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])  # the fish is the largest blob; tags/rulers are smaller
    x, y, bw, bh = stats[big, :4]
    gc = np.full((h, w), cv2.GC_BGD, np.uint8)
    pad = 25
    gc[max(0, y - pad):y + bh + pad, max(0, x - pad):x + bw + pad] = cv2.GC_PR_BGD
    gc[lbl == big] = cv2.GC_PR_FGD
    gc[cv2.erode((lbl == big).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0] = cv2.GC_FGD
    cv2.grabCut(im, gc, None, np.zeros((1, 65)), np.zeros((1, 65)), 4, cv2.GC_INIT_WITH_MASK)
    m = np.isin(gc, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(m)
    m = (lbl == 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])).astype(np.uint8)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    m = cv2.drawContours(np.zeros_like(m), cnts, -1, 1, -1)  # fill holes (eye, glare)
    x, y, bw, bh = cv2.boundingRect(m)
    rgba = np.dstack([im, m * 255])[y:y + bh, x:x + bw]
    name = os.path.splitext(os.path.basename(f))[0]
    cv2.imwrite(f"{OUT}/{name}.png", rgba)
    print(f"{name:40s} crop {bw}x{bh} aspect {bw / bh:.2f} fill {m.sum() / (bw * bh):.2f}")
