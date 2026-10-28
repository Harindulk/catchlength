"""The printed ArUco marker mat: generate it, find it in a photo, and rectify the photo to a top-down mm grid."""
from dataclasses import dataclass

import cv2
import numpy as np

DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


@dataclass(frozen=True)
class MatSpec:
    name: str
    width_mm: float
    height_mm: float
    marker_mm: float
    margin_mm: float
    per_long_side: int  # markers along the top and bottom edges
    per_short_side: int  # extra markers along the left and right edges (between the corners)
    first_id: int = 0  # tiles of one set use disjoint id ranges so each is found on its own

    def markers(self):
        """{id: (4,2) corner array in mm, clockwise from top-left}, laid out around the border."""
        m, s = self.margin_mm, self.marker_mm
        xs = np.linspace(m, self.width_mm - m - s, self.per_long_side)
        ys = np.linspace(m, self.height_mm - m - s, self.per_short_side + 2)[1:-1]
        tl = [(x, m) for x in xs] + [(x, self.height_mm - m - s) for x in xs]
        tl += [(m, y) for y in ys] + [(self.width_mm - m - s, y) for y in ys]
        return {self.first_id + i: np.array([[x, y], [x + s, y], [x + s, y + s], [x, y + s]], np.float32) for i, (x, y) in enumerate(tl)}


# A1 holds about a dozen frigate-sized tunas; A4 is the "try it at home with a pen" mat.
MATS = {
    "A1": MatSpec("A1", 841, 594, 60, 15, 7, 3),
    "A3": MatSpec("A3", 420, 297, 40, 10, 5, 1),
    "A4": MatSpec("A4", 297, 210, 30, 8, 4, 1),
}


def render(spec: MatSpec, px_per_mm: float = 4.0, grid_mm: int = 100) -> np.ndarray:
    """Top-down image of the mat (white, black markers, faint 10 cm grid, a 10 cm check bar)."""
    w, h = round(spec.width_mm * px_per_mm), round(spec.height_mm * px_per_mm)
    img = np.full((h, w), 255, np.uint8)
    for g in range(grid_mm, int(spec.width_mm), grid_mm):
        cv2.line(img, (round(g * px_per_mm), 0), (round(g * px_per_mm), h), 236, max(1, round(px_per_mm * 0.4)))
    for g in range(grid_mm, int(spec.height_mm), grid_mm):
        cv2.line(img, (0, round(g * px_per_mm)), (w, round(g * px_per_mm)), 236, max(1, round(px_per_mm * 0.4)))
    for i, c in spec.markers().items():
        side = round(spec.marker_mm * px_per_mm)
        mk = cv2.aruco.generateImageMarker(DICT, i, side)
        x, y = np.round(c[0] * px_per_mm).astype(int)
        img[y:y + side, x:x + side] = mk
    # printers rescale: the user checks this bar with a ruler before trusting any number
    bx, by = spec.margin_mm + spec.marker_mm + 10, spec.height_mm - spec.margin_mm - spec.marker_mm - 8
    p0, p1 = (round(bx * px_per_mm), round(by * px_per_mm)), (round((bx + 100) * px_per_mm), round(by * px_per_mm))
    cv2.line(img, p0, p1, 0, max(1, round(px_per_mm * 0.6)))
    cv2.putText(img, f"CatchLength {spec.name} - this bar is 100 mm", (p0[0], p0[1] - round(2 * px_per_mm)),
                cv2.FONT_HERSHEY_SIMPLEX, px_per_mm * 0.12, 120, max(1, round(px_per_mm * 0.25)))
    return img


@dataclass
class MatFix:
    H: np.ndarray  # image px -> mat mm
    n_markers: int
    reproj_mm: float  # RMS corner error after the fit, on the mat
    reproj_px: float = 0.0  # the same error in image pixels: what the camera can actually resolve


def detect(image_bgr: np.ndarray, spec: MatSpec) -> MatFix | None:
    """Find the mat's markers and fit image->mat homography. None if fewer than 4 markers are visible."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr
    corners, ids, _ = cv2.aruco.ArucoDetector(DICT, cv2.aruco.DetectorParameters()).detectMarkers(gray)
    if ids is None:
        return None
    ref = spec.markers()
    src, dst = [], []
    for c, i in zip(corners, ids.ravel()):
        if int(i) in ref:
            src.append(c.reshape(4, 2))
            dst.append(ref[int(i)])
    if len(src) < 4:
        return None
    src, dst = np.concatenate(src), np.concatenate(dst)
    H, _ = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
    if H is None:
        return None
    err = cv2.perspectiveTransform(src[None], H)[0] - dst
    err_px = cv2.perspectiveTransform(dst[None], np.linalg.inv(H))[0] - src
    return MatFix(H, len(src) // 4, float(np.sqrt((err ** 2).sum(1).mean())), float(np.sqrt((err_px ** 2).sum(1).mean())))


def rectify(image_bgr: np.ndarray, fix: MatFix, spec: MatSpec, px_per_mm: float = 2.0) -> np.ndarray:
    """Warp the photo so 1 px = 1/px_per_mm mm on the mat plane."""
    S = np.diag([px_per_mm, px_per_mm, 1.0])
    size = (round(spec.width_mm * px_per_mm), round(spec.height_mm * px_per_mm))
    return cv2.warpPerspective(image_bgr, S @ fix.H, size, flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))


def marker_mask(spec: MatSpec, px_per_mm: float, pad_mm: float = 4) -> np.ndarray:
    """1 where a marker (plus padding) sits in the rectified frame, so segmentation can ignore it."""
    m = np.zeros((round(spec.height_mm * px_per_mm), round(spec.width_mm * px_per_mm)), np.uint8)
    for c in spec.markers().values():
        x0, y0 = ((c[0] - pad_mm) * px_per_mm).astype(int)
        x1, y1 = ((c[2] + pad_mm) * px_per_mm).astype(int)
        m[max(0, y0):y1, max(0, x0):x1] = 1
    bx, by = spec.margin_mm + spec.marker_mm + 10, spec.height_mm - spec.margin_mm - spec.marker_mm - 8
    m[int((by - 12) * px_per_mm):int((by + 3) * px_per_mm), int((bx - 2) * px_per_mm):int((bx + 200) * px_per_mm)] = 1
    return m


def tile(spec: MatSpec, k: int) -> MatSpec:
    """Tile k of a set: same layout, its own marker ids. DICT_4X4_50 has 50 ids, so A4 (10 markers) allows 5 tiles."""
    n = len(spec.markers())
    assert (k + 1) * n <= 50, "out of marker ids"
    return MatSpec(f"{spec.name} tile {k + 1}", spec.width_mm, spec.height_mm, spec.marker_mm, spec.margin_mm,
                   spec.per_long_side, spec.per_short_side, first_id=k * n)


def detect_tiles(image_bgr: np.ndarray, spec: MatSpec, n_tiles: int) -> dict[int, MatFix]:
    """Fit every visible tile. Tiles lying flat on one surface share a plane, so any one of them measures
    true lengths anywhere on it (a rigid move between tiles doesn't change distances): no alignment needed."""
    fixes = {k: detect(image_bgr, tile(spec, k)) for k in range(n_tiles)}
    return {k: f for k, f in fixes.items() if f is not None}


def length_mm(fix: MatFix, p0, p1) -> float:
    """Distance on the mat plane between two image points (px)."""
    a, b = cv2.perspectiveTransform(np.float32([[p0, p1]]), fix.H)[0]
    return float(np.linalg.norm(a - b))
