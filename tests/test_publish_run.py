"""publish_run copies a graded run into web/samples/<id>/ and puts it first in index.json."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("publish_run", Path(__file__).parent.parent / "scripts/publish_run.py")
publish_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish_run)


def test_publish_run(tmp_path):
    run, samples = tmp_path / "runs/IMG_0001", tmp_path / "samples"
    run.mkdir(parents=True)
    samples.mkdir()
    (samples / "index.json").write_text(json.dumps([{"id": "museum", "label": "Flags a fish"}, {"id": "field-tray1", "label": "old"}]))
    with pytest.raises(SystemExit, match="run.json"):  # ungraded folder
        publish_run.publish(run, "field-tray1", "Real fish", samples)
    for name in publish_run.FILES:
        (run / name).write_text(name)
    with pytest.raises(SystemExit, match="--id"):
        publish_run.publish(run, "Field Tray", "Real fish", samples)

    out = publish_run.publish(run, "field-tray1", "Real fish, tape-checked", samples)
    assert out == samples / "field-tray1" and (out / "run.json").read_text() == "run.json"
    assert sorted(p.name for p in out.iterdir()) == sorted(publish_run.FILES)
    assert json.loads((samples / "index.json").read_text()) == [  # first, and the same id replaced rather than doubled
        {"id": "field-tray1", "label": "Real fish, tape-checked"}, {"id": "museum", "label": "Flags a fish"}]
