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


@pytest.fixture
def robot_stack(tmp_path):
    """A session wired to a real bridge over a deliberately slow sim backend."""
    import random

    from hub.kit_study.robot_bridge import RobotBridge
    from hub.kit_study.robotd.sim import SimBackend

    bus = MessageBus()
    db = Database(tmp_path / "hri.db")
    ctrl = RecordingController(bus, db, tmp_path / "recordings")
    backend = SimBackend(timing={"home": 0.2, "pick": 0.2, "place": 0.2, "open_gripper": 0.2,
                                 "noise_std": 0.0}, rng=random.Random(0))
    bridge = RobotBridge(bus, backend, monitor_interval=5.0)
    bridge.start()
    sess = KitSession(bus, db, ctrl, tick_interval=0.02, bridge=bridge,
                      default_profile={"lookahead": 1, "side": "C"})
    yield bus, db, ctrl, sess, bridge
    if sess.status() is not None:
        sess.stop()
    bridge.stop()


def test_stop_waits_for_the_in_flight_supply(robot_stack):
    """I3: a supply still running at teardown must not stage a part into the next session."""
    bus, db, ctrl, sess, bridge = robot_stack
    staged = []
    bus.subscribe("robot.part_staged", lambda m: staged.append(m["data"]["part_id"]))
    sess.start("P10", "C0", "orders_f1.yaml")
    t0 = time.time()
    while not bridge.busy() and time.time() - t0 < 2.0:
        time.sleep(0.01)
    assert bridge.busy(), "expected a supply job in flight"

    sess.stop()
    assert not bridge.busy(), "stop() returned while the robot was still moving"
    n = len(staged)
    time.sleep(0.3)
    assert len(staged) == n, "a part was staged after the session stopped"


def test_start_rejects_while_the_robot_is_still_busy(robot_stack):
    bus, db, ctrl, sess, bridge = robot_stack
    bridge.submit("home")                       # 0.2 s of motion
    with pytest.raises(RuntimeError, match="robot busy"):
        sess.start("P11", "C0", "orders_f1.yaml")
    assert ctrl.status() is None, "the rejected start must not leave a recording behind"
    assert bridge.wait_idle(2.0)
    assert sess.start("P11", "C0", "orders_f1.yaml")["recording_id"] is not None
    sess.stop()


def test_busy_start_maps_to_409(robot_stack):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from hub.kit_study.router import build_kit_router

    bus, db, ctrl, sess, bridge = robot_stack
    app = FastAPI()
    app.include_router(build_kit_router(sess, bus, bridge))
    with TestClient(app) as c:
        bridge.submit("home")
        r = c.post("/api/kit/session/start", json={"participant_code": "P12", "condition": "C0"})
        assert r.status_code == 409 and "robot busy" in r.json()["detail"]


def test_robot_and_supply_markers_are_labelled(robot_stack):
    """I5: which part went to which slot must be recoverable from the recording."""
    bus, db, ctrl, sess, bridge = robot_stack
    info = sess.start("P13", "C0", "orders_f1.yaml")
    t0 = time.time()
    while not any(m["label"].startswith("staged:") for m in db.get_recording(info["recording_id"])["markers"]):
        assert time.time() - t0 < 3.0, "no staged marker was recorded"
        time.sleep(0.02)
    bus.publish("wizard.mat_cleared", {})
    bridge.estop()
    sess.stop()
    labels = [m["label"] for m in db.get_recording(info["recording_id"])["markers"]]
    assert any(l == "staged:F1O1P1@C" for l in labels)
    assert any(l.startswith("decision:lookahead=1:F1O1P1@C") for l in labels)
    assert "mat_cleared" in labels
    assert "estop:estop:wizard" in labels


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
    # a stopped block leaves its questionnaires pending; the next block waits for them
    with pytest.raises(RuntimeError, match="questionnaires pending"):
        sess.start("P01", "C1", "orders_f1.yaml")
    sess.skip_questionnaires("test")
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

    # Once that unrelated recording is stopped (and the post-block questionnaires are
    # dealt with), a fresh session starts cleanly.
    ctrl.stop()
    sess.skip_questionnaires("test")
    info2 = sess.start("P08", "C0", "orders_f1.yaml")
    assert info2["recording_id"] is not None
    sess.stop()
