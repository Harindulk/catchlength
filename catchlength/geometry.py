"""Fish length from a mask, on the mat plane, and IOTC-style length-frequency bins."""
import cv2
import numpy as np


def to_plane(H: np.ndarray, pts_px: np.ndarray) -> np.ndarray:
    return cv2.perspectiveTransform(np.float32(pts_px).reshape(1, -1, 2), H)[0]


def axis_length_mm(mask: np.ndarray, H: np.ndarray) -> tuple[float, np.ndarray]:
    """Length of the mask along its main axis, measured on the mat plane (so perspective doesn't bias it).
    Returns (mm, the two image-space end points). For a straight fish this is snout-to-tail-tip (total length);
    fork length comes from the fork point, so the agent treats this as an upper bound / cross-check."""
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cnts, key=cv2.contourArea).reshape(-1, 2).astype(np.float32)
    p = to_plane(H, c)
    mean = p.mean(0)
    axis = np.linalg.svd(p - mean, full_matrices=False)[2][0]
    t = (p - mean) @ axis
    i0, i1 = int(np.argmin(t)), int(np.argmax(t))
    return float(t[i1] - t[i0]), c[[i0, i1]]


def points_length_mm(H: np.ndarray, p0, p1) -> float:
    a, b = to_plane(H, np.array([p0, p1]))
    return float(np.linalg.norm(a - b))


def lf_bins(lengths_cm, width_cm: int = 1) -> dict[int, int]:
    """Counts per class, keyed by the class's lower bound in cm (IOTC wants intervals of at most 5 cm)."""
    assert 1 <= width_cm <= 5, "IOTC drops size samples binned coarser than 5 cm"
    out: dict[int, int] = {}
    for x in lengths_cm:
        k = int(np.floor(x / width_cm) * width_cm)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))
