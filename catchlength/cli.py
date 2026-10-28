"""Run the agent on a clip or photo: python -m catchlength.cli data/raw/<day>/clip.mp4 [--frames 6] [--budget 0.6]
Writes runs/<name>/run.json (the full log, report and per-fish rows) plus overlay.jpg for the console."""
import argparse
import csv
import hashlib
import io
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from .agent import Run, run_agent
from .rules import RULES
from .api import Client


def sharpness(frame: np.ndarray) -> float:
    """Variance of the Laplacian on a 640 px copy: low means motion blur or missed focus."""
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    s = 640 / max(g.shape)
    return float(cv2.Laplacian(cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.CV_64F).var())


def pick_frames(frames: list[np.ndarray], n: int) -> list[np.ndarray]:
    """Keep the n sharpest frames that show at least one marker tile, in time order. A phone clip panned by hand
    has blurred frames; Spark should choose among frames that can already be measured."""
    from .mat import MATS, detect_tiles
    scored = [(i, sharpness(f), len(detect_tiles(f, MATS["A4"], 4))) for i, f in enumerate(frames)]
    usable = [x for x in scored if x[2]] or scored
    keep = sorted(sorted(usable, key=lambda x: -x[1])[:n])
    return [frames[i] for i, _, _ in keep]


def load_frames(path: str, n: int, candidates: int = 24) -> list[np.ndarray]:
    img = cv2.imread(path)
    if img is not None:
        return [img]
    cap = cv2.VideoCapture(path)  # OpenCV applies the file's rotation flag, so frames come out as displayed
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []
    for i in np.linspace(0, max(0, total - 1), max(n, candidates)).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, f = cap.read()
        if ok:
            frames.append(f)
    if not frames:
        raise SystemExit(f"can't read {path}")
    if max(frames[0].shape[:2]) > 1920:  # 4K -> 1080p: SAM and Spark don't need more, and it's cheaper
        s = 1920 / max(frames[0].shape[:2])
        frames = [cv2.resize(f, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) for f in frames]
    return pick_frames(frames, n)


def catch_csv(run: Run) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["fish_id", "species", "fork_cm", "outline_cm", "status", "reason", "tile", "rule_results"])
    for f in run.fish.values():
        r = f.row()
        w.writerow([r["id"], r["species"], r["fork_cm"], r["axis_cm"], r["status"], r["why"], r["tile"],
                    ";".join(f"{x['rule']}={x['result']}" for x in r["rules"])])
    return buf.getvalue()


def receipt(run: Run, path: str, csv_text: str) -> dict:
    """What a reviewer needs to trust or reproduce the run, without trusting us."""
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = ""
    fixes = run.fixes.values()
    return {"clip_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest() if path and Path(path).is_file() else None,
            "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "models": sorted({c["model"] for c in run.client.ledger}), "git_commit": commit or None,
            "calibration": {"tiles": sorted(run.fixes), "corner_error_px": max((f.reproj_px for f in fixes), default=None)},
            "fish": {"detected": len(run.fish), "accepted": sum(f.status == "measured" for f in run.fish.values()),
                     "flagged": sum(f.status == "needs_review" for f in run.fish.values())},
            "rescued": [f.det.id for f in run.fish.values() if int(f.det.id) >= 1000],
            "frames": {"best": run.best, "checked": sorted({k for f in run.fish.values() for k in f.frames})},
            "csv_sha256": hashlib.sha256(csv_text.encode()).hexdigest(),
            "cost_usd": round(run.client.spent, 4)}


def save(run: Run, out: Path, path: str = "") -> None:
    out.mkdir(parents=True, exist_ok=True)
    csv_text = catch_csv(run)
    (out / "catch.csv").write_text(csv_text)
    cv2.imwrite(str(out / "overlay.jpg"), run.outlined(), [cv2.IMWRITE_JPEG_QUALITY, 85])
    cv2.imwrite(str(out / "frame.jpg"), run.frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    (out / "run.json").write_text(json.dumps({
        "source": run.source, "status": run.status, "plan": run.plan, "best_frame": run.best, "size": run.size,
        "tiles": sorted(run.fixes), "log": run.log, "reviews": run.reviews, "report": run.report,
        "fish": [f.row() | {"points": f.points, "box": [float(v) for v in f.det.box], "outline": _outline(f.det.mask)}
                 for f in run.fish.values()],
        "cost": {"usd": round(run.client.spent, 4), "calls": len(run.client.ledger),
                 "cached": sum(c["cached"] for c in run.client.ledger)},
        "rules_cited": {k: RULES[k] for k in sorted({x["rule"] for f in run.fish.values() for x in f.rules if x["rule"]})},
        "receipt": receipt(run, path, csv_text)}, indent=1, default=str))


def _outline(mask: np.ndarray) -> list:
    """The mask as a simplified polygon in frame pixels, for the console's SVG overlay."""
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cnts, key=cv2.contourArea)
    return cv2.approxPolyDP(c, 2.0, True).reshape(-1, 2).tolist()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--frames", type=int, default=6)
    ap.add_argument("--budget", type=float, default=0.60)
    ap.add_argument("--out", default="runs")
    a = ap.parse_args()
    run = run_agent(Run(load_frames(a.path, a.frames), Client(a.budget), Path(a.path).name))
    out = Path(a.out) / Path(a.path).stem
    save(run, out, a.path)
    print(f"{run.status}: {len(run.fish)} fish, ${run.client.spent:.3f}, {len(run.log)} turns -> {out}/run.json")


if __name__ == "__main__":
    main()
