"""SAM 3.1 over the Meta Model API: one concept prompt or box/point prompts in, full-frame masks out."""
import base64
from dataclasses import dataclass

import cv2
import numpy as np
from meta_sam_parser import (CompletedOutcome, FramePrompt, PromptBox, PromptObject, PromptPoint, build_object_prompt,
                             decode_mask_to_raster, image_segmentation_format)

MODEL = "sam-3.1"
USD_PER_IMAGE = 0.0025


@dataclass
class Detection:
    id: str
    box: tuple[float, float, float, float]  # left, top, right, bottom (half-open), image px
    mask: np.ndarray  # bool, full frame
    confidence: float | None = None

    @property
    def area(self) -> int:
        return int(self.mask.sum())


def data_url(image_bgr: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()


def request(image_bgr: np.ndarray, text: str) -> dict:
    return {"model": MODEL, "metadata": {"include_confidence": "true"},
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": text}, {"type": "input_image", "image_url": data_url(image_bgr)}]}]}


def parse(output_text: str, size: tuple[int, int]) -> list[Detection]:
    """Turn SAM's output text into detections. Empty text is zero matches, not an error."""
    w, h = size
    p = image_segmentation_format().create_parser()
    p.push(output_text)
    recs = p.finish(CompletedOutcome()).result.records
    boxes = {r.object_id: r for r in recs if type(r).__name__ == "SegmentationBoxRecord"}
    out = []
    for r in recs:
        if type(r).__name__ != "SegmentationMaskRecord":
            continue
        m = np.frombuffer(decode_mask_to_raster(r.mask), np.uint8).reshape(r.mask.height, r.mask.width)
        full = np.zeros((h, w), bool)
        b = r.bounds
        bw, bh = int(b.right - b.left), int(b.bottom - b.top)
        if m.shape != (bh, bw):  # the raster is box-local and may be coarser than the box: stretch it over the box
            m = cv2.resize(m, (bw, bh), interpolation=cv2.INTER_NEAREST)
        full[b.top:b.top + m.shape[0], b.left:b.left + m.shape[1]] = m[:h - b.top, :w - b.left] > 0
        bx = boxes.get(r.object_id)
        box = (bx.left, bx.top, bx.right, bx.bottom) if bx else (b.left, b.top, b.right, b.bottom)
        out.append(Detection(r.object_id, box, full, r.confidence if r.confidence is not None else getattr(bx, "confidence", None)))
    return out


def rescue_prompt(size: tuple[int, int], targets: list[dict]) -> str:
    """targets: [{id, box:(l,t,r,b), negatives:[(x,y), ...]}] -> object-prompt text.
    The negative points sit on neighbouring fish so SAM doesn't swallow them into the new mask."""
    w, h = size
    clamp = lambda x, y: (max(0, min(w - 1, int(x))), max(0, min(h - 1, int(y))))
    objs = []
    for t in targets:
        l, tp, r, b = t["box"]
        (l, tp), (r, b) = clamp(l, tp), clamp(r, b)
        pts = [PromptPoint(*clamp(x, y), label="negative") for x, y in t.get("negatives", [])]
        objs.append(PromptObject(id=int(t["id"]), prompts=[FramePrompt(box=PromptBox(l, tp, r + 1, b + 1), points=pts)]))
    return build_object_prompt(size=size, objects=objs)
