import cv2
import numpy as np

from catchlength.mat import MATS, detect, detect_tiles, length_mm, render, tile

PX = 4.0  # px per mm when composing the synthetic floor


def floor_with_tiles(offsets_mm, size_mm=(900, 600)):
    """White floor with A4 tiles pasted at arbitrary (unaligned) offsets and small rotations."""
    floor = np.full((round(size_mm[1] * PX), round(size_mm[0] * PX)), 255, np.uint8)
    for k, (x, y, rot) in enumerate(offsets_mm):
        img = render(tile(MATS["A4"], k), px_per_mm=PX)
        h, w = img.shape
        M = cv2.getRotationMatrix2D((w / 2, h / 2), rot, 1.0)
        M[:, 2] += (x * PX, y * PX)
        mask = cv2.warpAffine(np.full_like(img, 255), M, floor.shape[::-1])
        warped = cv2.warpAffine(img, M, floor.shape[::-1])
        floor[mask > 0] = warped[mask > 0]
    return floor


def phone_view(floor, seed=0):
    """Oblique 'phone' photo of the floor; returns the image and the floor->image homography."""
    h, w = floor.shape
    rng = np.random.default_rng(seed)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = src * 0.5 + rng.uniform(-60, 60, (4, 2)).astype(np.float32) + 80
    G = cv2.getPerspectiveTransform(src, dst)
    out = cv2.warpPerspective(cv2.cvtColor(floor, cv2.COLOR_GRAY2BGR), G, (w // 2 + 200, h // 2 + 200),
                              borderValue=(200, 200, 200))
    return out, G


def to_img(G, p_mm):
    return cv2.perspectiveTransform(np.float32([[np.array(p_mm) * PX]]), G)[0, 0]


def test_tiles_found_independently_and_measure_anywhere_on_the_plane():
    floor = floor_with_tiles([(20, 20, 3), (560, 300, -7)])
    img, G = phone_view(floor)
    fixes = detect_tiles(img, MATS["A4"], 2)
    assert set(fixes) == {0, 1}
    # a 400 mm "fish" lying between the tiles, outside both of them
    a, b = to_img(G, (330, 120)), to_img(G, (730, 120))
    for f in fixes.values():
        assert abs(length_mm(f, a, b) - 400) < 4  # within 1%


def test_tile_ids_dont_collide():
    ids = [set(tile(MATS["A4"], k).markers()) for k in range(5)]
    assert all(not (ids[i] & ids[j]) for i in range(5) for j in range(i + 1, 5))
    assert detect(render(tile(MATS["A4"], 1), px_per_mm=PX), MATS["A4"]) is None  # tile 0 spec ignores tile 1
