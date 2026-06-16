import pytest

from hub.bus import MessageBus
from hub.experiments.controller import RecordingController
from hub.experiments.db import Database


@pytest.fixture
def setup(tmp_path):
    db = Database(tmp_path / "hri.db")
    exp = db.create_experiment("S", "")
    db.set_conditions(exp, ["Baseline"])
    cond = db.get_experiment(exp)["conditions"][0]["id"]
    part = db.create_participant(exp, "P01", "")
    ctrl = RecordingController(MessageBus(), db, tmp_path / "recordings")
    return db, ctrl, exp, part, cond


def test_start_marker_stop(setup):
    db, ctrl, exp, part, cond = setup
    res = ctrl.start(experiment_id=exp, participant_id=part, condition_id=cond)
    rec_id = res["recording_id"]
    assert ctrl.status()["recording_id"] == rec_id
    ctrl.marker("Robot error", "button")
    st = ctrl.status()
    assert st["sample_count"] >= 0 and len(st["markers"]) == 1
    ctrl.stop()
    assert ctrl.status() is None
    assert db.get_recording(rec_id)["status"] == "completed"
    assert db.get_recording(rec_id)["markers"][0]["label"] == "Robot error"


def test_only_one_active(setup):
    db, ctrl, exp, part, cond = setup
    ctrl.start(experiment_id=exp, participant_id=part, condition_id=cond)
    with pytest.raises(RuntimeError):
        ctrl.start(experiment_id=exp, participant_id=part, condition_id=cond)
    ctrl.stop()


def test_start_reuses_session_when_given(setup):
    db, ctrl, exp, part, cond = setup
    r1 = ctrl.start(experiment_id=exp, participant_id=part, condition_id=cond)
    ctrl.stop()
    r2 = ctrl.start(session_id=r1["session_id"], condition_id=cond)
    ctrl.stop()
    assert r1["session_id"] == r2["session_id"]


def test_marker_without_active_raises(setup):
    db, ctrl, exp, part, cond = setup
    with pytest.raises(RuntimeError):
        ctrl.marker("x", "button")
