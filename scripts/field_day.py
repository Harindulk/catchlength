"""Field day in one command. python scripts/field_day.py data/raw/<day> [--manual-s 300 --film-s 90]
1. Runs the agent on every video in the folder (.mp4/.mov/.m4v, not subfolders: put b-roll and to-camera clips in
   broll/). Stills and the sheet photo are left alone. Cached, so re-running is free -> runs/<clip>/.
2. For each run without tags.json, writes a stub listing its fish ids: fill each with "<batch>-<tag>" by looking at
   runs/<clip>/overlay.jpg (the masking-tape number beside each head), "x" for something that isn't a tape fish,
   and set "batch" (or "skip" for a clip that isn't a measured batch).
3. When every run is tagged, grades them against ground_truth.csv -> web/benchmark.json, with the held-out bias
   split, tape repeatability and the stopwatch comparison (--manual-s: 10 fish by hand; --film-s: laying out and
   filming the same 10). If the sheet has a total_cm column, also compares the outline with the taped total length
   (scripts/tl_compare.py) -> web/benchmark_tl.json. The summary leads with mean difference and 95% limits."""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so `python scripts/field_day.py` finds the package from any folder

from catchlength.agent import Run, run_agent  # noqa: E402
from catchlength.api import Client  # noqa: E402
from catchlength.audit import grade, read_gt  # noqa: E402
from catchlength.cli import code_version, load_frames, save  # noqa: E402
from scripts.tl_compare import compare as compare_tl  # noqa: E402

VIDEO = {".mp4", ".mov", ".m4v"}


def main(day: Path, runs_dir: Path = ROOT / "runs", out: Path = ROOT / "web/benchmark.json",
         new_client=lambda: Client(0.60), manual_s: float | None = None, film_s: float | None = None) -> dict:
    clips = sorted(p for p in day.iterdir() if p.is_file() and p.suffix.lower() in VIDEO)
    if not clips:
        sys.exit(f"No videos in {day} (looked for {', '.join(sorted(VIDEO))})")
    runs = []
    for clip in clips:
        d = runs_dir / clip.stem
        if not (d / "run.json").exists():
            t0 = time.time()
            run = run_agent(Run(load_frames(str(clip), 6), new_client(), clip.name))
            save(run, d, str(clip))
            rj = json.loads((d / "run.json").read_text())
            rj["wall_s"] = round(time.time() - t0, 1)  # agent time for the stopwatch comparison
            (d / "run.json").write_text(json.dumps(rj, indent=1, default=str))
            print(f"{clip.name}: {run.status}, {len(run.fish)} fish, ${run.client.spent:.3f}, {rj['wall_s']} s")
        tags = d / "tags.json"
        if not tags.exists():
            fish = [f["id"] for f in json.loads((d / "run.json").read_text())["fish"]]
            tags.write_text(json.dumps({"batch": "", "tags": {f: "" for f in fish}}, indent=1))
            print(f"  label {d}/overlay.jpg -> {tags}")
        runs.append(d)

    meta = {r: json.loads((r / "tags.json").read_text()) for r in runs}
    todo = [str(r) for r, m in meta.items() if not m["batch"] or (m["batch"] != "skip" and not all(m["tags"].values()))]
    if todo:
        sys.exit(f"Tag these runs first: {', '.join(todo)}")
    try:
        gt = read_gt(day / "ground_truth.csv")
    except (OSError, ValueError) as e:
        sys.exit(f"Fix the ground truth first: {e}")
    graded = [r for r, m in meta.items() if m["batch"] != "skip"]
    rj = {r: json.loads((r / "run.json").read_text()) for r in graded}
    res = grade(gt, [{"source": rj[r]["source"], "batch": meta[r]["batch"], "tags": meta[r]["tags"], "fish": rj[r]["fish"]}
                     for r in graded])
    timed = [j for j in rj.values() if j.get("wall_s") and j["cost"]["cached"] < j["cost"]["calls"]]  # a full cache replay isn't a timing
    n = sum(len(j["fish"]) for j in timed)
    res["timing"] = {"manual_s_per_fish": round(manual_s / 10, 1) if manual_s else None,
                     "film_s_per_fish": round(film_s / 10, 1) if film_s else None,
                     "agent_s_per_fish": round(sum(j["wall_s"] for j in timed) / n, 1) if n else None, "runs_timed": len(timed)}
    res["code"] = code_version()
    out.write_text(json.dumps(res, indent=1))
    L, H = res["length_accepted_only"], res["held_out"]
    tl_line = "total length: no total_cm column on the sheet"
    if any("total_cm" in r for r in gt):
        tl = compare_tl(gt, [{"tags": meta[r]["tags"], "fish": rj[r]["fish"]} for r in graded])
        out.with_name("benchmark_tl.json").write_text(json.dumps(tl, indent=1))
        tl_line = (f"total length (outline vs tape, {tl['n']} fish): mean diff {tl.get('mean_diff_cm')} cm, 95% limits {tl.get('loa95')}"
                   f" -> {out.with_name('benchmark_tl.json')}")
    else:
        out.with_name("benchmark_tl.json").unlink(missing_ok=True)  # a stale one from an earlier sheet must not stay published
    print(f"fork length (accepted, {L['n']} fish): mean diff {L.get('bias')} cm, 95% limits {L.get('loa95')}; {tl_line}")
    print(f"{res['n_measured']} fish: MAE {L['mae']} cm on accepted, within 2 cm {L.get('within_2cm')}, "
          f"count exact {res['count']['exact_rate']}, species {res['species']['accuracy']}, pass marks {res['pass_marks']}\n"
          f"held out ({H['held_out_raw']['n']} fish): MAE {H['held_out_raw']['mae']} raw, {H['held_out_corrected']['mae']} "
          f"after the {H['bias_fitted_cm']} cm bias fitted on the rest; tape repeat TEM {res['tape_repeat'].get('tem_cm')} cm; "
          f"seconds per fish: hand {res['timing']['manual_s_per_fish']}, agent {res['timing']['agent_s_per_fish']} "
          f"+ filming {res['timing']['film_s_per_fish']}; code {res['code']['describe']}"
          f"{'' if res['code']['frozen'] else ' (NOT the frozen version)'} -> {out}")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("day", type=Path)
    ap.add_argument("--manual-s", type=float, help="stopwatch: measuring and writing 10 fish by hand")
    ap.add_argument("--film-s", type=float, help="stopwatch: laying out, tagging and filming the same 10 fish")
    a = ap.parse_args()
    main(a.day, manual_s=a.manual_s, film_s=a.film_s)
