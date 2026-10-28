"""The whole loop on a synthetic scene, with a scripted stand-in for Muse Spark and SAM 3.1 (no key, no network)."""
import itertools
import json

import cv2
import numpy as np
import pytest

from catchlength import agent, sam, spark
from catchlength.api import Client
from catchlength.synth import det, make_scene, scripted_client

LENGTHS = [420, 380, 300, 250, 330]
POS = [(400, 130), (450, 330), (820, 140), (250, 520), (470, 545)]  # fish 3 and 4 lie end to end, touching


@pytest.fixture
def scene():
    return make_scene(LENGTHS, POS, angles=[5, -10, 8, 0, 0], seed=1)


def script(scene, tmp_path, monkeypatch, plan_count=5):
    monkeypatch.setattr("catchlength.api.CACHE", tmp_path)
    return scripted_client(scene, monkeypatch.setattr, plan_count)


def test_agent_rescues_merged_fish_measures_and_files(scene, tmp_path, monkeypatch):
    run = agent.run_agent(agent.Run([scene.image], script(scene, tmp_path, monkeypatch), "synthetic"))
    assert run.status == "awaiting_signoff", run.log[-1]
    assert [l["tool"] for l in run.log][:5] == ["inspect_clip", "calibrate", "segment", "find_missed", "rescue"]
    assert sorted(run.fish) == ["0", "1", "2", "2001", "2002"]  # merged "3" replaced by its two fish
    got = sorted(f.axis_mm for f in run.fish.values())
    for g, true in zip(got, sorted(LENGTHS)):
        assert abs(g - true) / true < 0.03  # outline length within 3% of the pasted length
    assert all(f.status == "measured" for f in run.fish.values()), [(k, f.why) for k, f in run.fish.items()]
    assert run.report["measured"] == 5 and sum(run.report["lf_1cm"].values()) == 5
    assert run.client.spent > 0 and len(run.client.ledger) > 10


def test_report_is_refused_until_the_count_is_explained(scene, tmp_path, monkeypatch):
    run = agent.run_agent(agent.Run([scene.image], script(scene, tmp_path, monkeypatch, plan_count=6), "synthetic"))
    assert run.status == "running" or run.status == "needs_review"
    assert any(l["tool"] == "submit_report" and l["result"].get("refused") for l in run.log)
    assert run.report is None


def test_three_refusals_escalate_to_the_officer(tmp_path, monkeypatch):
    run = agent.Run([np.full((400, 600, 3), 60, np.uint8)], Client(transport=lambda k, b: {}))
    for _ in range(3):
        r = run.calibrate()
    assert r["refused"] and "escalated" in r and run.status == "needs_review"
    assert run.reviews[0]["what"] == "calibrate"


def test_cross_frame_check_runs_on_clips_and_agrees_on_a_still_scene(scene, tmp_path, monkeypatch):
    client = script(scene, tmp_path, monkeypatch)
    run = agent.run_agent(agent.Run([scene.image, scene.image, scene.image], client, "synthetic clip"))
    m = next(l for l in run.log if l["tool"] == "measure")["result"]
    assert m["cross_frame"]["frames"] and all(f.status == "measured" for f in run.fish.values())
    assert all(len(f.frames) == 2 for f in run.fish.values() if f.det.id != "2001" and f.det.id != "2002")


def test_saved_run_has_csv_and_receipt(scene, tmp_path, monkeypatch):
    from catchlength.cli import save
    run = agent.run_agent(agent.Run([scene.image], script(scene, tmp_path, monkeypatch), "synthetic"))
    save(run, tmp_path / "out")
    saved = json.loads((tmp_path / "out/run.json").read_text())
    rc = saved["receipt"]
    assert rc["fish"] == {"detected": 5, "accepted": 5, "flagged": 0} and rc["rescued"] == ["2001", "2002"]
    assert rc["models"] == ["muse-spark-1.3", "sam-3.1"] and len(rc["csv_sha256"]) == 64
    assert (tmp_path / "out/catch.csv").read_text().count("\n") == 6 and (tmp_path / "out/overlay.jpg").exists()
