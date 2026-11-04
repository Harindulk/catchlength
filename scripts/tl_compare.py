"""Total length against the tape, the measure NARA reports: python scripts/tl_compare.py <ground_truth.csv> <run dir> [...]
The agent's outline length (end to end on the sheet, about total length) against a taped total length (`total_cm`
column, snout to tail tip). Added 4 Nov after the freeze, as a separate script so the frozen grader is untouched.
Reports the uncorrected mean difference with 95% limits of agreement (Bland-Altman), the design NARA used, on every
accepted fish with a taped total length. Writes web/benchmark_tl.json for the console's Benchmark tab."""
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def compare(gt_rows: list[dict], runs: list[dict]) -> dict:
    gt = {f"{r['batch']}-{r['tag']}": float(r["total_cm"].replace(",", ".")) for r in gt_rows if (r.get("total_cm") or "").strip()}
    pairs = []
    for run in runs:
        for f in run["fish"]:
            key = run["tags"].get(f["id"])
            if key in gt and f.get("axis_cm") is not None and f["status"] == "measured":
                pairs.append({"key": key, "tape_tl_cm": gt[key], "agent_outline_cm": f["axis_cm"]})
    d = np.array([p["agent_outline_cm"] - p["tape_tl_cm"] for p in pairs])
    if not len(d):
        return {"n": 0, "pairs": []}
    sd = float(d.std(ddof=1)) if len(d) > 1 else 0.0
    return {"n": len(d), "mean_diff_cm": round(float(d.mean()), 2), "loa95": [round(float(d.mean() - 1.96 * sd), 2), round(float(d.mean() + 1.96 * sd), 2)],
            "mae_cm": round(float(np.abs(d).mean()), 2), "within_1cm": round(float((np.abs(d) <= 1).mean()), 3), "pairs": pairs,
            "note": "outline length vs taped total length, accepted fish, no correction"}


def main() -> None:
    gt_path, run_dirs = sys.argv[1], sys.argv[2:]
    with open(gt_path, newline="", encoding="utf-8-sig") as fh:
        gt_rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(fh)]
    runs = []
    for d in map(Path, run_dirs):
        meta = json.loads((d / "tags.json").read_text())
        runs.append({"fish": json.loads((d / "run.json").read_text())["fish"], "tags": meta.get("tags", meta)})
    res = compare(gt_rows, runs)
    (ROOT / "web/benchmark_tl.json").write_text(json.dumps(res, indent=1))
    print(f"total length, n={res['n']}: mean diff {res.get('mean_diff_cm')} cm, 95% LoA {res.get('loa95')}")


if __name__ == "__main__":
    main()
