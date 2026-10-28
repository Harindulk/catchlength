"""Grade finished runs against the tape. The agent never sees this file's inputs.
python -m catchlength.audit data/raw/<day>/ground_truth.csv runs/<clip>/ [runs/<clip2>/ ...] --out data/benchmark.json
Each run folder needs tags.json: {"<fish_id>": "<batch>-<tag>", ...}, labelled by a person from overlay.jpg
(the masking-tape number beside each head). Fish with no tag are 'unmatched' and reported, never dropped."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

NAMES = {n.lower(): s["latin"] for s in json.loads((Path(__file__).parent.parent / "config/species.json").read_text())["species"]
         for n in (s["latin"], s["english"], s["sinhala"])}
KILL = {"mae_cm": 2.0, "min_fish": 40, "count_exact": 0.9, "species": 0.9}


def grade(gt_rows: list[dict], runs: list[dict]) -> dict:
    gt = {f"{r['batch']}-{r['tag']}": r for r in gt_rows}
    pairs, unmatched, clips = [], [], []
    for run in runs:
        tags, batch = run["tags"], run.get("batch")
        n_gt = sum(1 for r in gt_rows if r["batch"] == batch) if batch else None
        clips.append({"clip": run["source"], "detected": len(run["fish"]), "on_tape": n_gt,
                      "exact": n_gt is not None and len(run["fish"]) == n_gt})
        for f in run["fish"]:
            key = tags.get(f["id"])
            if key not in gt:
                unmatched.append({"clip": run["source"], "fish": f["id"]})
                continue
            g = gt[key]
            pairs.append({"key": key, "tape_cm": float(g["fork_cm"]), "agent_cm": f["fork_cm"], "status": f["status"],
                          "species_ok": None if not g.get("species") else _same(f["species"], g["species"])})
    measured = [p for p in pairs if p["agent_cm"] is not None]
    err = np.array([p["agent_cm"] - p["tape_cm"] for p in measured]) if measured else np.zeros(0)
    acc = np.array([p["agent_cm"] - p["tape_cm"] for p in measured if p["status"] == "measured"]) if measured else np.zeros(0)
    sp = [p["species_ok"] for p in pairs if p["species_ok"] is not None]
    out = {"n_matched": len(pairs), "n_measured": len(measured), "unmatched": unmatched,
           "length": _stats(err), "length_accepted_only": _stats(acc),
           "accepted": int(sum(p["status"] == "measured" for p in pairs)),
           "flagged": int(sum(p["status"] == "needs_review" for p in pairs)),
           "count": {"clips": clips, "exact_rate": _rate([c["exact"] for c in clips if c["on_tape"] is not None])},
           "species": {"n": len(sp), "accuracy": _rate(sp)}, "pairs": pairs}
    out["pass_marks"] = {
        "length": out["length_accepted_only"]["mae"] is not None and out["length_accepted_only"]["mae"] <= KILL["mae_cm"]
                  and out["n_measured"] >= KILL["min_fish"],
        "count": out["count"]["exact_rate"] is not None and out["count"]["exact_rate"] >= KILL["count_exact"],
        "species": out["species"]["accuracy"] is not None and out["species"]["accuracy"] >= KILL["species"]}
    return out


def _same(agent: str | None, tape: str) -> bool:
    """The tape sheet may say balaya, skipjack tuna or Katsuwonus pelamis; all mean the same fish."""
    return bool(agent) and agent.lower() == NAMES.get(tape.strip().lower(), tape.strip()).lower()


def _stats(e: np.ndarray) -> dict:
    if not len(e):
        return {"n": 0, "mae": None}
    a = np.abs(e)
    sd = float(e.std(ddof=1)) if len(e) > 1 else 0.0
    return {"n": len(e), "mae": round(float(a.mean()), 2), "median_ae": round(float(np.median(a)), 2),
            "p90_ae": round(float(np.percentile(a, 90)), 2), "within_2cm": round(float((a <= 2).mean()), 3),
            "bias": round(float(e.mean()), 2), "loa95": [round(float(e.mean() - 1.96 * sd), 2), round(float(e.mean() + 1.96 * sd), 2)]}


def _rate(xs) -> float | None:
    xs = list(xs)
    return round(sum(xs) / len(xs), 3) if xs else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ground_truth")
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", default="data/benchmark.json")
    a = ap.parse_args()
    gt = list(csv.DictReader(open(a.ground_truth)))
    runs = []
    for d in map(Path, a.runs):
        r = json.loads((d / "run.json").read_text())
        meta = json.loads((d / "tags.json").read_text())
        runs.append({"source": r["source"], "fish": r["fish"], "tags": meta.get("tags", meta), "batch": meta.get("batch")})
    res = grade(gt, runs)
    Path(a.out).write_text(json.dumps(res, indent=1))
    L = res["length_accepted_only"]
    print(f"{res['n_measured']} fish measured, MAE {L['mae']} cm (accepted only), within 2 cm {L.get('within_2cm')}, "
          f"count exact {res['count']['exact_rate']}, species {res['species']['accuracy']}, pass marks {res['pass_marks']}")


if __name__ == "__main__":
    main()
