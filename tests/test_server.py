import cv2

from catchlength import server
from catchlength.synth import make_scene, scripted_client

LENGTHS = [420, 380, 300, 250, 330]
POS = [(400, 130), (450, 330), (820, 140), (250, 520), (470, 545)]


def test_run_sample_streams_every_turn_and_saves(tmp_path, monkeypatch):
    scene = make_scene(LENGTHS, POS, angles=[5, -10, 8, 0, 0], seed=1)
    (tmp_path / "s1/frames").mkdir(parents=True)
    cv2.imwrite(str(tmp_path / "s1/frames/0.jpg"), scene.image)
    monkeypatch.setattr(server, "SAMPLES", tmp_path)
    monkeypatch.setattr(server, "OUT", tmp_path / "out")
    monkeypatch.setattr("catchlength.api.CACHE", tmp_path / "cache")
    # the frame went through JPEG, so the scripted stand-in must use masks only (it never reads pixels for SAM)
    events = []
    res = server.run_sample("s1", lambda e, d: events.append(e), scripted_client(scene, monkeypatch.setattr))
    assert events.count("turn") == len(res["log"]) and events[-1] == "done"
    assert res["status"] == "awaiting_signoff" and (tmp_path / "out/s1/frame.jpg").exists()


def test_unknown_and_sneaky_sample_ids_are_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SAMPLES", tmp_path)
    for sid in ["nope", "../etc", ".hidden"]:
        try:
            server.sample_frames(sid)
            assert False, sid
        except KeyError:
            pass


def test_per_ip_and_daily_caps(monkeypatch):
    monkeypatch.setattr(server, "PER_IP", 2)
    server._ledger.update(day=None)
    assert server.allow("1.1.1.1") is None and server.allow("1.1.1.1") is None
    assert "used today's" in server.allow("1.1.1.1")
    server._ledger["usd"] = server.DAILY_USD
    assert "budget" in server.allow("2.2.2.2")


def test_live_paths_cannot_climb_out(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "OUT", tmp_path / "runs/live")
    h = server.Handler.__new__(server.Handler)
    h.directory = str(server.WEB)
    assert "__missing__" in h.translate_path("/live/../../.env")
    assert h.translate_path("/live/s1/run.json").endswith("runs/live/s1/run.json")
    assert h.translate_path("/../.env").startswith(str(server.WEB))  # the static side keeps '..' inside web/


def test_signoff_is_recorded_once_and_only_for_real_runs(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(server, "OUT", tmp_path)
    (tmp_path / "s1").mkdir()
    (tmp_path / "s1/run.json").write_text(json.dumps({"status": "awaiting_signoff", "log": []}))
    rec = server.record_signoff("s1", True, "looks right")
    assert rec["status"] == "signed_off" and rec["log"][-1]["args"]["note"] == "looks right"
    for sid in ["s1", "../s1", "nope"]:  # already signed, path tricks, unknown
        try:
            server.record_signoff(sid, True, "")
            assert False, sid
        except KeyError:
            pass
