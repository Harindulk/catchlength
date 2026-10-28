"""Muse Spark 1.3 vision calls, each with a strict JSON schema. Images are downscaled to save tokens;
every coordinate comes back in the pixels of the image we sent and is scaled back here."""
import json
from pathlib import Path

import cv2
import numpy as np

from .api import Client
from .sam import data_url

MODEL = "muse-spark-1.3"
SPECIES = [s["latin"] for s in json.loads((Path(__file__).parent.parent / "config/species.json").read_text())["species"]]
PT = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
BOX = {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4}


def _shrink(img: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    s = min(1.0, max_side / max(img.shape[:2]))
    return (cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else img), s


def _ask(client: Client, name: str, prompt: str, images: list[np.ndarray], props: dict, est_usd: float = 0.01) -> dict:
    schema = {"type": "json_schema", "json_schema": {"name": name, "schema": {
        "type": "object", "properties": props, "required": list(props), "additionalProperties": False}}}
    content = [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": data_url(i)}} for i in images]
    out = client.call("chat", {"model": MODEL, "messages": [{"role": "user", "content": content}], "response_format": schema}, est_usd)
    return json.loads(out["choices"][0]["message"]["content"])


def plan(client: Client, frames: list[np.ndarray]) -> dict:
    small = [_shrink(f, 960)[0] for f in frames]
    return _ask(client, "plan", (
        f"These are {len(frames)} frames (index 0..{len(frames) - 1}) from a phone clip of fish laid on a sheet with printed "
        "black-and-white marker tiles, filmed to measure each fish. Say whether the clip is usable for measurement, list problems "
        "(blur, glare, fish cut off by the frame edge, fish stacked on each other, tiles not flat or not visible), pick the sharpest "
        "frame that shows every fish, count the whole fish you can see in that frame, and name the likely species."),
        small, {"usable": {"type": "boolean"}, "issues": {"type": "array", "items": {"type": "string"}},
                "best_frame": {"type": "integer"}, "expected_count": {"type": "integer"},
                "species_candidates": {"type": "array", "items": {"type": "string"}}, "tiles_visible": {"type": "integer"}})


def missed(client: Client, outlined: np.ndarray) -> dict:
    """The frame with SAM's outlines and numbers drawn on. Returns boxes for fish with no outline,
    and ids of outlines that cover more than one fish."""
    img, s = _shrink(outlined, 1280)
    h, w = img.shape[:2]
    r = _ask(client, "missed", (
        f"The image is {w}x{h} px. Each fish that was found has a coloured outline and a number. Count every whole fish. "
        "Give a tight box [left, top, right, bottom] in pixels of THIS image for each fish that has no outline of its own, "
        "and list the numbers of any outline that wraps two or more fish (touching fish merged into one)."),
        [img], {"count": {"type": "integer"}, "missed_boxes": {"type": "array", "items": BOX},
                "merged_ids": {"type": "array", "items": {"type": "string"}}})
    r["missed_boxes"] = [[v / s for v in b] for b in r["missed_boxes"]]
    return r


def keypoints(client: Client, crop: np.ndarray) -> dict:
    img, s = _shrink(crop, 768)
    h, w = img.shape[:2]
    r = _ask(client, "fork_points", (
        f"The image is {w}x{h} px and shows one fish. Give the pixel position of the tip of the snout (front of the upper jaw, "
        "mouth closed) and of the fork: the innermost point of the notch between the two tail lobes. If the tail fork isn't "
        "visible or the fish is badly curled, say so with low confidence."),
        [img], {"snout": PT, "fork": PT, "confidence": {"type": "number"}, "problem": {"type": "string"}}, 0.004)
    r["snout"], r["fork"] = [v / s for v in r["snout"]], [v / s for v in r["fork"]]
    return r


def species(client: Client, crop: np.ndarray) -> dict:
    img, _ = _shrink(crop, 768)
    return _ask(client, "species", (
        "Which of these species is the fish in the image? If it is none of them or you can't tell, answer unknown. "
        "Use the body shape, the stripes and spots, and the fins."),
        [img], {"species": {"type": "string", "enum": SPECIES + ["unknown"]}, "confidence": {"type": "number"},
                "evidence": {"type": "string"}}, 0.004)
