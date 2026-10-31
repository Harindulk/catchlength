"""The port-sampling agent. Muse Spark picks one tool per turn; code runs it and keeps the record.
Checks live inside the tools (the Agents 102 pattern): the model can't skip them, a refusal comes back as
feedback, and a tool refused 3 times hands the job to the officer instead of looping."""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import rules, sam, spark
from .api import Client
from .geometry import axis_length_mm, lf_bins, points_length_mm
from .mat import MATS, MatFix, detect_tiles

TILE = MATS["A4"]
N_TILES = 4
MAX_TURNS = 25
MAX_REFUSALS = 3
CAL_PX = 1.5  # worst tile-corner reprojection error before calibration refuses
FL_OVER_AXIS = (0.80, 1.0)  # fork length is shorter than snout-to-tail-tip; outside this band the two disagree
TL_TOL = 0.03  # outline (about TL) may differ this much from the species' published TL-from-FL before it's flagged
SNAP_PX = 8  # a fork point may sit this far outside the mask outline
SPREAD_MM = 10  # a fish's length may drift this much across frames before it's flagged
MATCH_MM = 40  # same fish in another frame = centroid within this distance on the same tile
TL_FROM_FL = {s["latin"]: s.get("tl_from_fl") for s in
              json.loads((Path(__file__).parent.parent / "config/species.json").read_text())["species"]}
THRESHOLDS = {"calibration_px": CAL_PX, "fl_over_outline": FL_OVER_AXIS, "tl_tolerance": TL_TOL, "snap_px": SNAP_PX,
              "drift_mm": SPREAD_MM, "match_mm": MATCH_MM, "rescue_area_x_median": (0.3, 3.0), "rescue_iou": 0.2,
              "species_conf": 0.5, "max_refusals": MAX_REFUSALS}  # what freeze tags and every receipt prints


@dataclass
class Fish:
    det: sam.Detection
    tile: int | None = None
    axis_mm: float | None = None
    fork_mm: float | None = None
    points: dict | None = None
    species: str | None = None
    species_conf: float | None = None
    rules: list = field(default_factory=list)
    status: str = "found"  # found | measured | needs_review
    why: str = ""
    frames: dict = field(default_factory=dict)  # frame index -> outline length mm, from the cross-frame check

    def row(self) -> dict:
        return {"id": self.det.id, "fork_cm": None if self.fork_mm is None else round(self.fork_mm / 10, 1),
                "axis_cm": None if self.axis_mm is None else round(self.axis_mm / 10, 1), "species": self.species,
                "species_conf": self.species_conf, "tile": self.tile, "status": self.status, "why": self.why,
                "sam_conf": self.det.confidence, "rules": self.rules,
                "frames_mm": {k: round(v, 1) for k, v in self.frames.items()}}


class Run:
    def __init__(self, frames: list[np.ndarray], client: Client, source: str = ""):
        self.frames, self.client, self.source = frames, client, source
        self.best = 0
        self.plan: dict = {}
        self.fixes: dict[int, MatFix] = {}
        self.fish: dict[str, Fish] = {}
        self.reviews: list[dict] = []
        self.refusals: dict[str, int] = {}
        self.log: list[dict] = []
        self.status = "running"  # running | needs_refilm | needs_review | awaiting_signoff | signed_off
        self.report: dict | None = None
        self._next_id = 1000

    @property
    def frame(self) -> np.ndarray:
        return self.frames[self.best]

    @property
    def size(self) -> tuple[int, int]:
        return self.frame.shape[1], self.frame.shape[0]

    # ---- helpers -------------------------------------------------------------------------------------------
    def refuse(self, tool: str, feedback: str) -> dict:
        n = self.refusals[tool] = self.refusals.get(tool, 0) + 1
        if n >= MAX_REFUSALS:
            self.reviews.append({"what": tool, "reason": f"refused {n} times: {feedback}", "by": "check"})
            self.status = "needs_review"
            return {"refused": True, "feedback": feedback, "escalated": "The officer now has this; stop and submit what you have."}
        return {"refused": True, "feedback": feedback, "tries_left": MAX_REFUSALS - n}

    def nearest_tile(self, pt) -> int | None:
        best, k = None, None
        for t, f in self.fixes.items():
            c = cv2.perspectiveTransform(np.float32([[[TILE.width_mm / 2, TILE.height_mm / 2]]]), np.linalg.inv(f.H))[0, 0]
            d = float(np.linalg.norm(c - pt))
            if best is None or d < best:
                best, k = d, t
        return k

    def crop(self, d: sam.Detection, pad: float = 0.15) -> tuple[np.ndarray, tuple[int, int]]:
        l, t, r, b = d.box
        px, py = (r - l) * pad, (b - t) * pad
        x0, y0 = max(0, int(l - px)), max(0, int(t - py))
        x1, y1 = min(self.size[0], int(r + px)), min(self.size[1], int(b + py))
        return self.frame[y0:y1, x0:x1], (x0, y0)

    def outlined(self) -> np.ndarray:
        img = self.frame.copy()
        for i, f in enumerate(self.fish.values()):
            col = tuple(int(c) for c in cv2.applyColorMap(np.uint8([[i * 37 % 255]]), cv2.COLORMAP_TURBO)[0, 0])
            cnts, _ = cv2.findContours(f.det.mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(img, cnts, -1, col, 3)
            x, y = int(f.det.box[0]), int(f.det.box[1])
            cv2.putText(img, f.det.id, (x, max(20, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, col, 2)
        return img

    # ---- tools (each one runs its own checks) --------------------------------------------------------------
    def inspect_clip(self) -> dict:
        self.plan = spark.plan(self.client, self.frames)
        self.best = max(0, min(len(self.frames) - 1, int(self.plan.get("best_frame", 0))))
        if not self.plan["usable"]:
            self.status = "needs_refilm"
            return {"refused": True, "feedback": "Clip not usable: " + "; ".join(self.plan["issues"]), "stop": True}
        return self.plan

    def calibrate(self) -> dict:
        self.fixes = detect_tiles(self.frame, TILE, N_TILES)
        if not self.fixes:
            return self.refuse("calibrate", "No marker tile found in the best frame. Ask for a re-film with a tile flat and in view.")
        worst = max(f.reproj_px for f in self.fixes.values())
        if worst > CAL_PX:
            return self.refuse("calibrate", f"Tile corners don't fit a flat sheet ({worst:.1f} px error): a tile is bent or "
                                            "lifted, or the frame is blurred. Measurements would be off.")
        return {"tiles": sorted(self.fixes), "corner_error_px": round(worst, 2),
                "corner_error_mm": round(max(f.reproj_mm for f in self.fixes.values()), 2)}

    def segment(self) -> dict:
        out = self.client.call("responses", sam.request(self.frame, "fish"), sam.USD_PER_IMAGE)
        dets = sam.parse(out.get("output_text") or _output_text(out), self.size)
        self.fish = {d.id: Fish(d) for d in dets}
        exp = self.plan.get("expected_count")
        return {"found": len(dets), "expected": exp, "ids": list(self.fish),
                "note": "count matches the plan" if exp == len(dets) else "count differs from the plan: look for missed or merged fish"}

    def find_missed(self) -> dict:
        return spark.missed(self.client, self.outlined())

    def rescue(self, boxes: list | None = None, split_ids: list | None = None) -> dict:
        """Send Spark's boxes back to SAM as box prompts, with negative points on the neighbours.
        Check: keep a new mask only if its area looks like one fish and it doesn't overlap the ones we have."""
        boxes, split_ids = boxes or [], [s for s in (split_ids or []) if s in self.fish]
        if not boxes:
            return self.refuse("rescue", "No boxes given. Call find_missed first and pass its missed_boxes.")
        med = float(np.median([f.det.area for f in self.fish.values()])) if self.fish else None
        keep = {k: f for k, f in self.fish.items() if k not in split_ids}
        targets = []
        for b in boxes:
            self._next_id += 1
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            neg = [tuple(np.argwhere(f.det.mask).mean(0)[::-1]) for f in keep.values()
                   if _box_iou(f.det.box, b) > 0 and not f.det.mask[int(min(cy, self.size[1] - 1)), int(min(cx, self.size[0] - 1))]]
            targets.append({"id": self._next_id, "box": b, "negatives": neg[:4]})
        out = self.client.call("responses", {**sam.request(self.frame, sam.rescue_prompt(self.size, targets))}, sam.USD_PER_IMAGE)
        new = sam.parse(out.get("output_text") or _output_text(out), self.size)
        accepted, rejected = [], []
        for d in new:
            ratio = d.area / med if med else 1.0
            overlap = max((_mask_iou(d.mask, f.det.mask) for f in keep.values()), default=0.0)
            lo, hi = THRESHOLDS["rescue_area_x_median"]
            if not lo <= ratio <= hi:
                rejected.append({"id": d.id, "why": f"area {ratio:.1f}x the median fish"})
            elif overlap >= THRESHOLDS["rescue_iou"]:
                rejected.append({"id": d.id, "why": f"overlaps an existing fish (IoU {overlap:.2f})"})
            else:
                accepted.append(d)
        for s in split_ids:  # a merged outline is only replaced when the rescue produced what's inside it
            inside = [d for d in accepted if _mask_iou(d.mask, self.fish[s].det.mask) > 0]
            if len(inside) >= 2:
                del self.fish[s]
            else:
                rejected.append({"id": s, "why": "merged outline kept: rescue didn't split it into 2+ fish"})
        for d in accepted:
            self.fish[d.id] = Fish(d)
        res = {"accepted": [d.id for d in accepted], "rejected": rejected, "count_now": len(self.fish)}
        if not accepted:
            return {**self.refuse("rescue", "Nothing passed the area/overlap check. Try tighter boxes, or request_review."), **res}
        return res

    def measure(self) -> dict:
        if not self.fixes:
            return self.refuse("measure", "Not calibrated. Call calibrate first.")
        flagged = []
        for f in self.fish.values():
            cy, cx = np.argwhere(f.det.mask).mean(0)
            f.tile = self.nearest_tile((cx, cy))
            H = self.fixes[f.tile].H
            f.axis_mm, _ = axis_length_mm(f.det.mask, H)
            crop, (x0, y0) = self.crop(f.det)
            kp = spark.keypoints(self.client, crop)
            sn, fk = np.add(kp["snout"], (x0, y0)), np.add(kp["fork"], (x0, y0))
            f.points = {"snout": sn.tolist(), "fork": fk.tolist(), "confidence": kp["confidence"]}
            dist = cv2.distanceTransform((~f.det.mask).astype(np.uint8), cv2.DIST_L2, 3)
            off = [float(dist[int(min(p[1], self.size[1] - 1)), int(min(p[0], self.size[0] - 1))]) for p in (sn, fk)]
            f.fork_mm = points_length_mm(H, sn, fk)
            ratio = f.fork_mm / f.axis_mm if f.axis_mm else 0
            if max(off) > SNAP_PX:
                f.status, f.why = "needs_review", f"a fork point is {max(off):.0f} px off the fish"
            elif not FL_OVER_AXIS[0] <= ratio <= FL_OVER_AXIS[1]:
                f.status, f.why = "needs_review", (f"fork length {f.fork_mm / 10:.1f} cm vs outline {f.axis_mm / 10:.1f} cm "
                                                   f"({ratio:.2f}); the two measurements disagree")
            else:
                f.status = "measured"
                self._check_tl(f)
            if f.status == "needs_review":
                flagged.append({"id": f.det.id, "why": f.why})
        cross = self._cross_frame(flagged)
        return {"measured": sum(f.status == "measured" for f in self.fish.values()), "flagged": flagged, "cross_frame": cross}

    def _cross_frame(self, flagged: list) -> dict:
        """Re-segment up to 2 other frames and re-measure every fish's outline there. A length that moves more than
        SPREAD_MM between frames means a bad mask or a bent fish: flag it, never average it away."""
        others = [i for i in np.linspace(0, len(self.frames) - 1, 3).astype(int) if i != self.best][:2]
        counts = {}
        for i in dict.fromkeys(others):
            fr = self.frames[i]
            fixes = detect_tiles(fr, TILE, N_TILES)
            out = self.client.call("responses", sam.request(fr, "fish"), sam.USD_PER_IMAGE)
            dets = sam.parse(out.get("output_text") or _output_text(out), (fr.shape[1], fr.shape[0]))
            counts[int(i)] = len(dets)
            for f in self.fish.values():
                if f.tile not in fixes:
                    continue
                me = _plane_centroid(self.fixes[f.tile].H, f.det.mask)
                cands = [(np.linalg.norm(_plane_centroid(fixes[f.tile].H, d.mask) - me), d) for d in dets]
                dist, d = min(cands, key=lambda c: c[0], default=(None, None))
                if d is not None and dist < MATCH_MM:
                    f.frames[int(i)] = axis_length_mm(d.mask, fixes[f.tile].H)[0]
        self._check_drift(flagged)
        return {"frames": counts, "best_frame_count": len(self.fish),
                "note": "counts agree across frames" if all(c == len(self.fish) for c in counts.values()) else
                        "counts differ across frames: a fish may be hidden, merged or cut off in some frames"}

    def _check_drift(self, flagged: list) -> None:
        for f in self.fish.values():
            if f.frames and f.axis_mm:
                spread = max(list(f.frames.values()) + [f.axis_mm]) - min(list(f.frames.values()) + [f.axis_mm])
                if spread > SPREAD_MM and f.status == "measured":
                    f.status, f.why = "needs_review", f"length drifts {spread / 10:.1f} cm across frames (limit {SPREAD_MM / 10:.0f} cm)"
                    flagged.append({"id": f.det.id, "why": f.why})

    def _check_tl(self, f: Fish) -> bool:
        """Species cross-check: the outline (about total length) against the TL the species' published TL-from-FL
        relationship predicts from this fork length. Runs after measure or classify, whichever comes second."""
        ab = TL_FROM_FL.get(f.species or "")
        if f.status != "measured" or not ab or not f.fork_mm or not f.axis_mm:
            return False
        tl = ab[0] * f.fork_mm / 10 + ab[1]
        off = f.axis_mm / 10 / tl - 1
        if abs(off) <= TL_TOL:
            return False
        f.status, f.why = "needs_review", (f"outline {f.axis_mm / 10:.1f} cm is {off:+.0%} from the {tl:.1f} cm total length "
                                           f"a {f.species} with this fork length should have (limit {TL_TOL:.0%})")
        return True

    def classify(self) -> dict:
        flagged = []
        for f in self.fish.values():
            r = spark.species(self.client, self.crop(f.det)[0])
            f.species, f.species_conf = (r["species"], r["confidence"]) if r["confidence"] >= THRESHOLDS["species_conf"] else ("unknown", r["confidence"])
            if self._check_tl(f):
                flagged.append({"id": f.det.id, "why": f.why})
        return {"species": {k: f.species for k, f in self.fish.items()}, "flagged": flagged}

    def apply_rules(self) -> dict:
        for f in self.fish.values():
            f.rules = rules.check_size(f.species or "unknown", (f.fork_mm or 0) / 10)
        return {"results": {k: [r["result"] for r in f.rules] for k, f in self.fish.items()}}

    def request_review(self, fish_id: str = "", reason: str = "") -> dict:
        self.reviews.append({"what": fish_id or "run", "reason": reason, "by": "agent"})
        if fish_id in self.fish:
            self.fish[fish_id].status, self.fish[fish_id].why = "needs_review", reason
        return {"queued": len(self.reviews)}

    def submit_report(self, summary: str = "") -> dict:
        problems = []
        for k, f in self.fish.items():
            if f.status == "found":
                problems.append(f"fish {k} has no length")
            if f.species is None:
                problems.append(f"fish {k} has no species (unknown is allowed)")
            if not f.rules:
                problems.append(f"fish {k} has no rule check")
        exp = self.plan.get("expected_count")
        if exp is not None and exp != len(self.fish) and not any(r["what"] == "run" for r in self.reviews):
            problems.append(f"count {len(self.fish)} differs from the {exp} expected; rescue the difference or request_review for the run")
        bad = rules.bad_citations(summary)
        if bad:
            problems.append(f"summary cites rules that don't exist: {bad}; cite only [rule:id] from the pack")
        if problems:
            return self.refuse("submit_report", "; ".join(problems))
        good = [f.fork_mm / 10 for f in self.fish.values() if f.status == "measured"]
        self.report = {"summary": summary, "fish": [f.row() for f in self.fish.values()], "lf_1cm": lf_bins(good),
                       "measured": len(good), "needs_review": len(self.fish) - len(good), "reviews": self.reviews,
                       "tiles": sorted(self.fixes), "source": self.source}
        self.status = "awaiting_signoff"
        return {"filed": True, "measured": len(good), "waiting_for": "officer sign-off"}


TOOLS = {
    "inspect_clip": ("Look at the clip: usable or not, the best frame, how many fish to expect, likely species.", {}),
    "calibrate": ("Find the marker tiles in the best frame and get real-world scale. Refuses if tiles are missing or bent.", {}),
    "segment": ("Ask SAM 3.1 for every fish in the best frame. Compare the count with the plan.", {}),
    "find_missed": ("Show Muse Spark the frame with SAM's outlines; get boxes for fish without an outline and ids of outlines "
                    "that merge two fish.", {}),
    "rescue": ("Send boxes back to SAM 3.1 (with negative points on neighbours) to segment missed fish or split merged ones. "
               "New masks must pass an area and overlap check.",
               {"boxes": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
                "split_ids": {"type": "array", "items": {"type": "string"}}}),
    "measure": ("Measure every fish two ways (outline length and snout-to-fork points). Fish where they disagree are flagged.", {}),
    "classify": ("Species for every fish from the closed list, or unknown.", {}),
    "apply_rules": ("Check each fish against the cited rule pack.", {}),
    "request_review": ("Hand a fish (or the whole run, fish_id='') to the officer with a reason, instead of guessing.",
                       {"fish_id": {"type": "string"}, "reason": {"type": "string"}}),
    "submit_report": ("File the report with a short summary for the officer. Cite rules as [rule:id]. Refused if anything is "
                      "unfinished.", {"summary": {"type": "string"}}),
}

SYSTEM = """You are a port-sampling officer's assistant at a Sri Lankan fish market. A phone clip shows fish laid on a sheet
with printed marker tiles. Your job: get a fork length, a species and a rule check for every fish, and file a report.
Use the tools, one per turn. Tools run their own checks: when one refuses, read the feedback and fix the cause; don't retry
blindly. If the clip is unusable, stop. If SAM's count differs from the plan, use find_missed then rescue. Never guess a
length or a species: hand anything you can't settle to the officer with request_review. Cite rules only as [rule:id]."""


def run_agent(run: Run, model: str = spark.MODEL, max_turns: int = MAX_TURNS, on_turn=None) -> Run:
    """The loop: the model decides, code acts, the result goes back. Stops when the report is filed, the clip is
    refused, the job is escalated, or the turn limit is hit."""
    tools = [{"type": "function", "function": {"name": n, "description": d, "parameters": {
        "type": "object", "properties": p, "additionalProperties": False}}} for n, (d, p) in TOOLS.items()]
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"New clip: {run.source or 'upload'}. Start."}]
    for turn in range(max_turns):
        # the Meta API accepts only tool_choice "auto" ("required" is HTTP 400), so a reply with no tool call gets a nudge
        out = run.client.call("chat", {"model": model, "messages": msgs, "tools": tools, "tool_choice": "auto"}, 0.01)
        m = out["choices"][0]["message"]
        msgs.append({k: v for k, v in m.items() if k in ("role", "content", "tool_calls") and v is not None})
        if not m.get("tool_calls"):
            run.log.append({"turn": turn, "tool": None, "args": {}, "result": {"said": (m.get("content") or "")[:300]}, "ms": 0,
                            "usd": round(run.client.spent, 4)})
            msgs.append({"role": "user", "content": "Call exactly one tool. The report isn't filed until submit_report accepts it."})
        for tc in (m.get("tool_calls") or [])[:1]:  # one tool per turn
            name, args = tc["function"]["name"], json.loads(tc["function"]["arguments"] or "{}")
            t0 = time.time()
            try:
                res = getattr(run, name)(**args) if name in TOOLS else {"refused": True, "feedback": f"no tool {name}"}
            except Exception as e:  # a tool crash goes back to the model as feedback, and into the log
                res = {"refused": True, "feedback": f"{type(e).__name__}: {e}"}
            run.log.append({"turn": turn, "tool": name, "args": args, "result": _brief(res), "ms": int((time.time() - t0) * 1000),
                            "usd": round(run.client.spent, 4)})
            if on_turn:
                on_turn(run.log[-1])  # the server streams each turn to the console as it happens
            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(_brief(res))})
        if run.status != "running":
            break
    else:
        run.reviews.append({"what": "run", "reason": f"turn limit {max_turns} reached", "by": "loop"})
        run.status = "needs_review"
    return run


def sign_off(run: Run, approve: bool, notes: str = "") -> Run:
    run.log.append({"turn": "officer", "tool": "sign_off", "args": {"approve": approve, "notes": notes}})
    run.status = "signed_off" if approve else "running"  # rejected notes go back to the agent on the next run_agent
    return run


def _brief(res: dict) -> dict:
    s = json.dumps(res, default=str)
    return res if len(s) < 3000 else {"truncated": s[:3000]}


def _output_text(out: dict) -> str:
    return "".join(c.get("text", "") for o in out.get("output", []) for c in (o.get("content") or []) if c.get("type") == "output_text")


def _plane_centroid(H: np.ndarray, mask: np.ndarray) -> np.ndarray:
    cy, cx = np.argwhere(mask).mean(0)
    return cv2.perspectiveTransform(np.float32([[[cx, cy]]]), H)[0, 0]


def _box_iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / u if u else 0.0


def _mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 0.0
