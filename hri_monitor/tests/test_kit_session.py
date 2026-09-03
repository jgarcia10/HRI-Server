import csv
import time

import pytest

from hub.bus import MessageBus
from hub.experiments.controller import RecordingController
from hub.experiments.db import Database
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
