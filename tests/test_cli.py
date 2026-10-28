import cv2
import numpy as np

from catchlength.cli import load_frames, pick_frames
from catchlength.synth import make_scene


def scene():
    return make_scene([400, 300], [(400, 150), (420, 480)], angles=[0, 5], seed=2).image


def test_pick_frames_drops_blurred_and_tileless_frames():
    sharp = scene()
    blurred = cv2.GaussianBlur(sharp, (0, 0), 6)
    empty = np.full_like(sharp, 60)  # no tiles in view
    frames = [blurred, sharp, empty, blurred, sharp]
    got = pick_frames(frames, 2)
    assert all(g is sharp for g in got)


def test_load_frames_from_a_clip(tmp_path):
    img = scene()
    h, w = img.shape[:2]
    path = str(tmp_path / "clip.mp4")
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    for k in range(30):  # every third frame blurred, as a hand-held pan would be
        vw.write(cv2.GaussianBlur(img, (0, 0), 5) if k % 3 == 0 else img)
    vw.release()
    frames = load_frames(path, 4)
    assert len(frames) == 4 and all(max(f.shape[:2]) <= 1920 for f in frames)  # 4K and odd sizes come out at 1080p-class
    from catchlength.cli import sharpness
    assert min(map(sharpness, frames)) > 2 * sharpness(cv2.GaussianBlur(frames[0], (0, 0), 5))  # none of the blurred ones
