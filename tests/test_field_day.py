"""Sunday's whole path on a synthetic clip: video in a day folder -> agent -> tags stub -> graded benchmark.json."""
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import cv2
import pytest

from catchlength.synth import make_scene, scripted_client

spec = importlib.util.spec_from_file_location("field_day", Path(__file__).parent.parent / "scripts/field_day.py")
field_day = importlib.util.module_from_spec(spec)
spec.loader.exec_module(field_day)

LENGTHS = [420, 380, 300, 250, 330]
POS = [(400, 130), (450, 330), (820, 140), (250, 520), (470, 545)]


def small_scene():
    """The test scene at 1800 px wide, so load_frames keeps it at the size the scripted masks were made for."""
    s = make_scene(LENGTHS, POS, angles=[5, -10, 8, 0, 0], seed=1)
    k = 1800 / s.image.shape[1]
    size = (1800, round(s.image.shape[0] * k) // 2 * 2)
    return replace(s, image=cv2.resize(s.image, size, interpolation=cv2.INTER_AREA),
                   masks=[cv2.resize(m.astype("uint8"), size, interpolation=cv2.INTER_NEAREST) > 0 for m in s.masks])


def test_field_day_runs_tags_and_grades(tmp_path, monkeypatch):
    scene = small_scene()
    monkeypatch.setattr("catchlength.api.CACHE", tmp_path / "cache")
    client = scripted_client(scene, monkeypatch.setattr)
    day, runs, out = tmp_path / "day", tmp_path / "runs", tmp_path / "benchmark.json"
    (day / "broll").mkdir(parents=True)
    h, w = scene.image.shape[:2]
    vw = cv2.VideoWriter(str(day / "IMG_0001.MOV"), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    for _ in range(20):
        vw.write(scene.image)
    vw.release()
    cv2.imwrite(str(day / "sheet.jpg"), scene.image)  # the photo of the paper sheet must not become a run
    (day / "broll" / "IMG_0002.MOV").write_bytes(b"")  # nor the b-roll

    with pytest.raises(SystemExit, match="Tag these runs first"):
        field_day.main(day, runs, out, lambda: client)
    assert sorted(p.name for p in runs.iterdir()) == ["IMG_0001"]
    stub = json.loads((runs / "IMG_0001/tags.json").read_text())
    assert sorted(stub["tags"]) == ["0", "1", "2", "2001", "2002"]

    # fish ids map to scene masks 0, 1, 2, 3, 4; the masking tape said 1..5. Tag 4 is in the held-out split.
    tags = {"0": "B1-1", "1": "B1-2", "2": "B1-3", "2001": "B1-4", "2002": "B1-5"}
    (runs / "IMG_0001/tags.json").write_text(json.dumps({"batch": "B1", "tags": tags}))
    fork = [round(L * 0.092, 1) for L in LENGTHS]  # the scripted fork point sits at 92% of the length
    rows = ["batch,tag,species,fork_cm,fork_cm_2,notes"] + [f"B1,{i + 1},balaya,{f},,"
                                                            for i, f in enumerate(fork)]
    rows[1] = f"B1,1,balaya,{fork[0]},{fork[0] + 0.5},"  # one fish taped twice
    (day / "ground_truth.csv").write_text("\n".join(rows + ["B1,1,balaya,40,,"]) + "\n")
    with pytest.raises(SystemExit, match="appears twice"):  # a duplicated tag is refused, not graded
        field_day.main(day, runs, out, lambda: client)

    (day / "ground_truth.csv").write_text("\n".join(rows) + "\n")
    res = field_day.main(day, runs, out, lambda: pytest.fail("a tagged run must not re-run"), manual_s=300)
    assert res == json.loads(out.read_text())
    assert res["n_matched"] == 5 and not res["unmatched"] and res["count"]["exact_rate"] == 1.0
    assert res["length"]["mae"] < 1.5 and res["species"]["accuracy"] == 1.0
    assert res["held_out"]["held_out_raw"]["n"] + res["held_out"]["fit"]["n"] == res["accepted"]
    assert res["tape_repeat"] == {"n": 1, "mean_abs_diff_cm": 0.5, "tem_cm": 0.35}
    assert res["timing"]["manual_s_per_fish"] == 30.0 and res["timing"]["agent_s_per_fish"] > 0
    assert "freeze_tag" in res["code"]
