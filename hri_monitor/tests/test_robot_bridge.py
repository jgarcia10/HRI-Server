import random
import threading
import time

from hub.bus import MessageBus
from hub.experiments.signals import RECORDED_TOPICS, sample_rows
from hub.kit_study.robot_bridge import RobotBridge
from hub.kit_study.robotd.base import ProtectiveStop
from hub.kit_study.robotd.sim import SimBackend


def make(**kw):
    bus = MessageBus()
    events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    backend = SimBackend(timing={"home": 0.01, "pick": 0.01, "place": 0.01, "open_gripper": 0.01,
                                 "noise_std": 0.0}, rng=random.Random(0), **kw)
    bridge = RobotBridge(bus, backend)
    bridge.start()
    return bridge, events, backend


def topics(events):
    return [t for t, _ in events]


def test_supply_publishes_lifecycle_and_part_staged():
    bridge, events, _ = make()
    job = bridge.supply("F1O1P1", "BL1", "L")
    assert bridge.wait_idle(2.0)
    ts = topics(events)
    assert ts.index("robot.skill_queued") < ts.index("robot.skill_started") < ts.index("robot.part_staged")
    staged = next(d for t, d in events if t == "robot.part_staged")
    assert staged == {"part_id": "F1O1P1", "depot_slot": "BL1", "slot": "L", "job_id": job}
    done = [d for t, d in events if t == "robot.skill_done"]
    assert done and done[-1]["skill"] == "supply" and done[-1]["duration_s"] >= 0
    assert "robot.state" in ts
    bridge.stop()


def test_failure_publishes_skill_failed_and_keeps_running():
    bridge, events, _ = make(failure_rate=1.0)
    bridge.supply("F1O1P1", "BL1", "L")
    assert bridge.wait_idle(2.0)
    failed = [d for t, d in events if t == "robot.skill_failed"]
    assert failed and failed[0]["protective_stop"] is False and "grasp" in failed[0]["error"]
    assert "robot.part_staged" not in topics(events)
    # bridge still accepts work
    bridge.submit("home")
    assert bridge.wait_idle(2.0)
    bridge.stop()


def test_estop_clears_queue_and_publishes():
    slow = SimBackend(timing={"home": 0.3, "pick": 0.3, "place": 0.3, "open_gripper": 0.3, "noise_std": 0.0},
                      rng=random.Random(0))
    bus2 = MessageBus(); ev2 = []
    bus2.subscribe("*", lambda m: ev2.append(m["topic"]))
    b2 = RobotBridge(bus2, slow); b2.start()
    for _ in range(5):
        b2.submit("home")
    time.sleep(0.05)
    dropped = b2.clear_queue()
    assert dropped >= 3 and b2.queue_size() == 0
    b2.submit("home"); b2.submit("home")
    b2.estop()
    assert b2.queue_size() == 0
    assert "robot.estop" in ev2
    b2.stop()


def test_protective_stop_flagged():
    class PS(SimBackend):
        def pick(self, depot_slot):
            raise ProtectiveStop("protective stop")
    bus = MessageBus(); ev = []
    bus.subscribe("robot.skill_failed", lambda m: ev.append(m["data"]))
    b = RobotBridge(bus, PS(rng=random.Random(0))); b.backend.connect(); b.start()
    b.supply("P", "RD1", "C")
    assert b.wait_idle(2.0)
    assert ev and ev[0]["protective_stop"] is True
    b.stop()


def test_signals_mapping():
    assert {"robot.skill_done", "robot.part_staged", "robot.skill_failed", "robot.estop"} <= RECORDED_TOPICS
    assert sample_rows("robot.skill_done", {"job_id": "j", "skill": "supply", "args": {}, "duration_s": 4.2}) == \
        [("robot.skill_duration_s", 4.2)]
    assert sample_rows("robot.part_staged", {"part_id": "x", "depot_slot": "RD1", "slot": "L", "job_id": "j"}) == \
        [("robot.part_staged", 1.0)]
    assert sample_rows("robot.state", {"connected": True}) == []


def test_wait_idle_not_true_while_job_claimed():
    """wait_idle must return False while a job is claimed, even if queue is empty."""
    class BlockingHome(SimBackend):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._gate = threading.Event()
        def home(self):
            self._gate.wait(1.0)

    bus = MessageBus(); ev = []
    bus.subscribe("*", lambda m: ev.append((m["topic"], m["data"])))
    backend = BlockingHome(timing={"home": 0.01, "pick": 0.01, "place": 0.01, "open_gripper": 0.01,
                                   "noise_std": 0.0}, rng=random.Random(0))
    bridge = RobotBridge(bus, backend)
    bridge.start()
    bridge.submit("home")
    time.sleep(0.02)  # let worker dequeue and set _active
    bridge.clear_queue()
    # queue is empty but job is still running
    assert bridge.wait_idle(0.05) is False
    backend._gate.set()  # release the blocking home
    assert bridge.wait_idle(1.0) is True
    bridge.stop()


def test_stop_then_start_processes_jobs():
    """stop() then start() should allow the bridge to process new jobs."""
    bridge, events, _ = make()
    j1 = bridge.submit("home")
    assert bridge.wait_idle(2.0)
    done1 = [d for t, d in events if t == "robot.skill_done"]
    assert len(done1) == 1
    bridge.stop()

    # Clear events and restart
    events.clear()
    bridge.start()
    j2 = bridge.submit("home")
    assert bridge.wait_idle(2.0)
    done2 = [d for t, d in events if t == "robot.skill_done"]
    assert len(done2) == 1
    bridge.stop()
