import csv
import time

import pytest

from hub.bus import MessageBus
from hub.experiments.controller import RecordingController
from hub.experiments.db import Database
from hub.kit_study.orders import KIND_SEQUENCE
from hub.kit_study.session import EXPERIMENT_NAME, KitSession


@pytest.fixture
def stack(tmp_path):
    bus = MessageBus()
    db = Database(tmp_path / "hri.db")
    ctrl = RecordingController(bus, db, tmp_path / "recordings")
    sess = KitSession(bus, db, ctrl, tick_interval=0.02)
    yield bus, db, ctrl, sess
    sess.stop()


def test_start_creates_experiment_and_recording(stack):
    bus, db, ctrl, sess = stack
    info = sess.start("P01", "C0", "orders_f1.yaml")
    assert set(info) >= {"recording_id", "session_id", "condition"}
    exps = db.list_experiments()
    exp = next(e for e in exps if e["name"] == EXPERIMENT_NAME)
    names = [c["name"] for c in db.get_experiment(exp["id"])["conditions"]]
    assert names == ["C0", "C1"]
    assert ctrl.status()["recording_id"] == info["recording_id"]
    assert sess.engine.state()["phase"] == "running"


def test_double_start_rejected(stack):
    _, _, _, sess = stack
    sess.start("P01", "C0", "orders_f1.yaml")
    with pytest.raises(RuntimeError):
        sess.start("P01", "C1", "orders_f1.yaml")


def test_markers_and_rows_recorded(stack, tmp_path):
    bus, db, ctrl, sess = stack
    info = sess.start("P02", "C1", "orders_f1.yaml")
    eng = sess.engine
    for _ in range(eng.state()["n_parts"]):
        eng.mark_part_placed()          # completes O1
    time.sleep(0.1)                     # let the ticker run a few times
    out = sess.stop()
    assert out["recording_id"] == info["recording_id"]
    rec = db.get_recording(info["recording_id"])
    labels = [m["label"] for m in rec["markers"]]
    assert any(l.startswith("order_started:O1") for l in labels)
    assert any(l.startswith("order_completed:O1") for l in labels)
    with open(rec["csv_path"]) as f:
        signals = {row["signal"] for row in csv.DictReader(f)}
    assert "task.part_placed" in signals


def test_reuses_existing_experiment(stack):
    bus, db, ctrl, sess = stack
    sess.start("P01", "C0", "orders_f1.yaml")
    sess.stop()
    sess.start("P01", "C1", "orders_f1.yaml")
    assert len([e for e in db.list_experiments() if e["name"] == EXPERIMENT_NAME]) == 1
    sess.stop()


def test_start_failure_cleans_up_recording_and_subscription(stack, monkeypatch):
    bus, db, ctrl, sess = stack
    # Force TaskEngine.start_block() to raise
    from hub.kit_study.task_engine import TaskEngine
    original_start_block = TaskEngine.start_block
    def failing_start_block(self):
        raise ValueError("simulated start_block failure")
    monkeypatch.setattr(TaskEngine, "start_block", failing_start_block)

    # Attempt to start; expect exception to propagate
    with pytest.raises(ValueError, match="simulated start_block failure"):
        sess.start("P01", "C0", "orders_f1.yaml")

    # Verify cleanup: no active recording and _info is None
    assert ctrl.status() is None, "recording should be stopped"
    assert sess._info is None, "_info should be None"
    assert sess.engine is None, "engine should be None"

    # Verify subsequent start succeeds (bus subscription and controller are clean)
    monkeypatch.setattr(TaskEngine, "start_block", original_start_block)
    info = sess.start("P01", "C0", "orders_f1.yaml")
    assert info["recording_id"] is not None
    sess.stop()


def test_stop_publishes_final_idle_task_state(stack):
    bus, db, ctrl, sess = stack
    seen = []
    bus.subscribe("task.state", lambda m: seen.append(m["data"]))
    sess.start("P06", "C0", "orders_f1.yaml")
    sess.stop()
    assert seen, "expected at least one task.state publish"
    assert seen[-1] == {
        "phase": "idle",
        "order_index": -1,
        "order_id": None,
        "kind": None,
        "step_index": 0,
        "n_parts": 0,
        "current_part": None,
        "remaining_s": None,
        "queue": list(KIND_SEQUENCE),
        "perturbation_applied": False,
    }


def test_wizard_events_recorded_as_markers(stack):
    bus, db, ctrl, sess = stack
    info = sess.start("P07", "C0", "orders_f1.yaml")
    bus.publish("wizard.speech", {"text": "give me the red one"})
    bus.publish("wizard.reposition", {"slot": "L"})
    bus.publish("wizard.speech", {"text": "x" * 200})       # must be truncated
    sess.stop()
    rec = db.get_recording(info["recording_id"])
    labels = [m["label"] for m in rec["markers"]]
    assert "speech:give me the red one" in labels
    assert "reposition:L" in labels
    truncated = next(l for l in labels if l.startswith("speech:xxx"))
    assert len(truncated) == len("speech:") + 120


def test_stop_does_not_kill_an_unrelated_recording(stack):
    bus, db, ctrl, sess = stack
    info = sess.start("P08", "C0", "orders_f1.yaml")

    # Something external stops our recording out from under the session...
    stopped = ctrl.stop()
    assert stopped["recording_id"] == info["recording_id"]

    # ...and a new, unrelated recording is started against the same session row.
    exp = next(e for e in db.list_experiments() if e["name"] == EXPERIMENT_NAME)
    cond_id = next(c["id"] for c in db.get_experiment(exp["id"])["conditions"]
                  if c["name"] == "C0")
    new_rec = ctrl.start(condition_id=cond_id, session_id=info["session_id"])

    # KitSession.stop() must not tear down that unrelated recording.
    out = sess.stop()
    assert ctrl.status() is not None
    assert ctrl.status()["recording_id"] == new_rec["recording_id"]
    assert out.get("recording_id") is None      # our stop() skipped controller.stop()
    assert sess._info is None and sess.engine is None

    # Once that unrelated recording is stopped, a fresh session starts cleanly.
    ctrl.stop()
    info2 = sess.start("P08", "C0", "orders_f1.yaml")
    assert info2["recording_id"] is not None
    sess.stop()
