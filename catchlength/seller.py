"""The seller's copy of a run: each fish's fork length and an estimated weight from a published length-weight curve,
with the formula and its source. Evidence for the sale, never a price. Only fish the agent accepted get a length;
flagged fish say they wait for the officer. Built from run.json, so it never changes a number the agent filed."""
import json
from pathlib import Path

SPECIES = {s["latin"]: s for s in json.loads((Path(__file__).parent.parent / "config/species.json").read_text())["species"]}


def weight_kg(species: str | None, fork_cm: float | None) -> tuple[float | None, str]:
    """Round weight from W = a * FL^b, or None with the reason no weight is given."""
    s = SPECIES.get(species or "")
    if not s or not s.get("w_from_fl"):
        return None, "no published fork-length weight curve for this species"
    if fork_cm is None:
        return None, "no length"
    lo, hi = s.get("w_fl_range_cm") or (0, 1e9)
    if not lo <= fork_cm <= hi:
        return None, f"outside the {lo}-{hi} cm range the curve was fitted on"
    a, b = s["w_from_fl"]
    return round(a * fork_cm ** b, 2), ""


def size_receipt(run: dict) -> dict:
    fish, used = [], {}
    for f in run.get("fish", []):
        ok = f["status"] == "measured"
        w, why = weight_kg(f["species"], f["fork_cm"]) if ok else (None, "")
        sp = SPECIES.get(f["species"] or "")
        name = (sp["english"] + (f" ({sp['sinhala']})" if sp["sinhala"] else "")) if sp else (f["species"] or "unknown")
        row = {"id": f["id"], "species": f["species"], "name": name, "fork_cm": f["fork_cm"] if ok else None, "est_weight_kg": w,
               "note": why if ok else "waiting for the fisheries officer's check"}
        fish.append(row)
        if w is not None:
            s = SPECIES[f["species"]]
            used[f["species"]] = {"formula": f"W(kg) = {s['w_from_fl'][0]:g} x FL(cm)^{s['w_from_fl'][1]:g}",
                                  "source": s["w_source"], "url": s["w_url"]}
    rc = run.get("receipt") or {}
    return {"title": "Size receipt", "purpose": "Evidence for the sale: what was measured and how. It doesn't set a price.",
            "signed_off": run["status"] == "signed_off", "status": run["status"], "fish": fish, "curves": used,
            "weights_note": "Weights are estimated from length with a published curve, not weighed. One fish can be heavier or lighter than the curve says.",
            "measured_utc": rc.get("finished_utc"), "clip_sha256": rc.get("clip_sha256"), "csv_sha256": rc.get("csv_sha256"),
            "code": rc.get("describe") or rc.get("git_commit")}


def as_text(r: dict) -> str:
    """Plain text for a WhatsApp message."""
    lines = [f"CatchLength {r['title'].lower()}: {r['purpose']}",
             "Officer signed off." if r["signed_off"] else "Not yet signed off by the fisheries officer."]
    for f in r["fish"]:
        name = f["name"]
        if f["fork_cm"] is None:
            lines.append(f"Fish {f['id']}: {f['note']}")
        else:
            w = f"about {f['est_weight_kg']:.2f} kg (estimate)" if f["est_weight_kg"] is not None else "no weight estimate"
            lines.append(f"Fish {f['id']}, {name}: fork length {f['fork_cm']:.1f} cm, {w}")
    lines += [f"{k}: {v['formula']} ({v['source']})" for k, v in r["curves"].items()]
    lines.append(r["weights_note"])
    if r["clip_sha256"]:
        lines.append(f"Clip fingerprint {r['clip_sha256'][:16]}")
    return "\n".join(lines)
