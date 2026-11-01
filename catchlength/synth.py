"""Synthetic scenes for tests and the pre-field benchmark: museum cut-outs (public domain, pre-hackathon reference)
pasted at known lengths next to marker tiles, then seen through an oblique 'phone' camera."""
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

import itertools
import json

from . import agent, sam
from .api import Client
from .mat import MATS, render, tile

PX = 3.0  # px per mm on the synthetic floor
ROOT = Path(__file__).parent.parent


@dataclass
class Scene:
    image: np.ndarray  # BGR, camera view
    masks: list[np.ndarray]  # bool, camera view, one per fish
    total_mm: list[float]  # snout to tail tip, the length we pasted at
    species: list[str]
    G: np.ndarray  # floor px -> camera px


# cut-outs whose GrabCut mask is the fish alone (others still carry the museum tag, which would corrupt the length)
CLEAN = ["euthynnus_affinis_USNM-443215", "katsuwonus_pelamis_USNM-403110", "rastrelliger_kanagurta_USNM-445241",
         "katsuwonus_pelamis_USNM-403111", "euthynnus_affinis_USNM-403363", "katsuwonus_pelamis_USNM-403112"]


def make_scene(lengths_mm, positions_mm, angles=None, seed=0, tiles=((20, 20), (640, 400)), floor_mm=(1000, 650)):
    rng = np.random.default_rng(seed)
    cuts = [str(ROOT / f"data/cutouts/{c}.png") for c in CLEAN]
    fh, fw = round(floor_mm[1] * PX), round(floor_mm[0] * PX)
    floor = np.full((fh, fw, 3), (40, 45, 50), np.uint8)  # dark plastic sheet
    for k, (x, y) in enumerate(tiles):
        t = cv2.cvtColor(render(tile(MATS["A4"], k), px_per_mm=PX), cv2.COLOR_GRAY2BGR)
        floor[round(y * PX):round(y * PX) + t.shape[0], round(x * PX):round(x * PX) + t.shape[1]] = t
    masks, species = [], []
    for i, (L, (x, y)) in enumerate(zip(lengths_mm, positions_mm)):
        c = cv2.imread(cuts[i % len(cuts)], cv2.IMREAD_UNCHANGED)
        s = L * PX / c.shape[1]
        c = cv2.resize(c, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        ang = angles[i] if angles else float(rng.uniform(-25, 25))
        M = cv2.getRotationMatrix2D((c.shape[1] / 2, c.shape[0] / 2), ang, 1.0)
        M[:, 2] += (x * PX - c.shape[1] / 2, y * PX - c.shape[0] / 2)
        a = cv2.warpAffine(c[:, :, 3], M, (fw, fh)) > 127
        rgb = cv2.warpAffine(c[:, :, :3], M, (fw, fh))
        floor[a] = rgb[a]
        for m in masks:  # later fish lie on top
            m &= ~a
        masks.append(a)
        species.append(" ".join(Path(cuts[i % len(cuts)]).stem.split("_")[:2]).capitalize())
    src = np.float32([[0, 0], [fw, 0], [fw, fh], [0, fh]])
    dst = np.float32([[90, 40], [fw * 0.62, 10], [fw * 0.66, fh * 0.6], [40, fh * 0.56]])
    G = cv2.getPerspectiveTransform(src, dst)
    size = (int(fw * 0.7), int(fh * 0.65))
    img = cv2.warpPerspective(floor, G, size, borderValue=(90, 90, 90))
    cam_masks = [cv2.warpPerspective(m.astype(np.uint8), G, size, flags=cv2.INTER_NEAREST) > 0 for m in masks]
    return Scene(img, cam_masks, list(map(float, lengths_mm)), species, G)


def det(i, m):
    ys, xs = np.nonzero(m)
    return sam.Detection(str(i), (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1), m, 0.9)


def scripted_client(scene, patch, plan_count=5, client_kw=None):
    """A stand-in for Muse Spark and SAM 3.1 that knows the scene's true masks: for tests and the labelled simulated
    sample only. patch(obj, name, value) swaps the model calls (monkeypatch.setattr in tests)."""
    merged = scene.masks[3] | scene.masks[4]
    sam_outputs = {"fish": [det(i, m) for i, m in enumerate(scene.masks[:3])] + [det(3, merged)],
                   "rescue": [det(2001, scene.masks[3]), det(2002, scene.masks[4])]}
    patch(agent.sam, "parse", lambda text, size: sam_outputs[text])

    probe = agent.Run([scene.image], None)

    def fork_points(client, crop):  # stand-in for Spark: true mask of the fish this crop was cut around, fork at 92%
        for m in scene.masks:
            c, (x0, y0) = probe.crop(det(0, m))
            if c.shape == crop.shape:
                pts = (np.argwhere(m)[:, ::-1] - (x0, y0)).astype(float)
                break
        mean = pts.mean(0)
        ax = np.linalg.svd(pts - mean, full_matrices=False)[2][0]
        t = (pts - mean) @ ax
        a, b = pts[np.argmin(t)], pts[np.argmax(t)]
        f = a + 0.92 * (b - a)
        edge = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]
        edge = max(edge, key=cv2.contourArea).reshape(-1, 2) - (x0, y0)
        f = edge[np.argmin(((edge - f) ** 2).sum(1))].astype(float)  # a real fork point sits on the notch edge, the outline
        return {"snout": a.tolist(), "fork": f.tolist(), "confidence": 0.8, "problem": ""}
    patch(agent.spark, "keypoints", fork_points)

    submit = ("submit_report", {"summary": "5 fish measured. Skipjack has no gazetted minimum [rule:lk-finfish-no-min]."})
    steps = itertools.chain([("inspect_clip", {}), ("calibrate", {}), ("segment", {}), ("find_missed", {}), ("rescue", None),
                  ("measure", {}), ("classify", {}), ("apply_rules", {}),
                  submit], itertools.repeat(submit))  # a stubborn model keeps submitting
    state = {}

    def transport(kind, body):
        if kind == "responses":
            text = body["input"][0]["content"][0]["text"]
            return {"output_text": "fish" if text == "fish" else "rescue"}
        if "tools" in body:  # the agent model: pick the next tool, reading results like a model would
            name, args = next(steps)
            if name == "rescue":
                args = {"boxes": state["missed"]["missed_boxes"], "split_ids": state["missed"]["merged_ids"]}
            return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": name, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}]}
        schema = body["response_format"]["json_schema"]["name"]
        reply = {"plan": {"usable": True, "issues": [], "best_frame": 0, "expected_count": plan_count,
                          "species_candidates": ["Katsuwonus pelamis"], "tiles_visible": 2},
                 "missed": {"count": 5, "missed_boxes": [list(map(float, det(0, scene.masks[k]).box)) for k in (3, 4)],
                            "merged_ids": ["3"]},
                 "species": {"species": "Katsuwonus pelamis", "confidence": 0.9, "evidence": "stripes on belly"}}[schema]
        if schema == "missed":
            state["missed"] = reply
        return {"choices": [{"message": {"content": json.dumps(reply)}}], "usage": {"prompt_tokens": 1000, "completion_tokens": 100}}

    return Client(transport=transport, **(client_kw or {}))
