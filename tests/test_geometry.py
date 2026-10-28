import cv2
import numpy as np

from catchlength.geometry import axis_length_mm, lf_bins, points_length_mm


def test_axis_length_survives_perspective():
    # a 300 x 60 mm ellipse "fish" on the plane at 2 px/mm, viewed obliquely
    plane = np.zeros((400, 800), np.uint8)
    cv2.ellipse(plane, (400, 200), (300, 60), 25, 0, 360, 1, -1)
    S = np.diag([2.0, 2.0, 1.0])  # mm -> plane px
    G = cv2.getPerspectiveTransform(np.float32([[0, 0], [800, 0], [800, 400], [0, 400]]),
                                    np.float32([[60, 30], [700, 0], [760, 420], [0, 380]]))
    img = cv2.warpPerspective(plane, G, (800, 450), flags=cv2.INTER_NEAREST)
    H = np.linalg.inv(G @ S)  # image px -> mm
    mm, ends = axis_length_mm(img, H)
    assert abs(mm - 300) < 4
    assert abs(points_length_mm(H, *ends) - mm) < 0.5  # end points sit on the outline, close to the axis


def test_lf_bins():
    assert lf_bins([41.2, 41.9, 42.0, 47.5]) == {41: 2, 42: 1, 47: 1}
    assert lf_bins([41.2, 44.9, 45.0], 5) == {40: 2, 45: 1}
