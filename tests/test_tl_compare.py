import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from tl_compare import compare  # noqa: E402


def test_outline_vs_taped_total_length_uses_accepted_fish_only():
    gt = [{"batch": "B1", "tag": "1", "total_cm": "30.0"}, {"batch": "B1", "tag": "2", "total_cm": "40,0"}, {"batch": "B1", "tag": "3", "total_cm": ""}]
    run = {"tags": {"0": "B1-1", "1": "B1-2", "2": "B1-3"}, "fish": [
        {"id": "0", "axis_cm": 30.5, "status": "measured"}, {"id": "1", "axis_cm": 39.5, "status": "measured"},
        {"id": "2", "axis_cm": 20.0, "status": "measured"}]}
    r = compare(gt, [run])
    assert r["n"] == 2 and r["mean_diff_cm"] == 0.0 and r["within_1cm"] == 1.0  # tag 3 has no taped total length
    run["fish"][0]["status"] = "needs_review"
    assert compare(gt, [run])["n"] == 1
