import random
import threading
import time

from hub.bus import MessageBus
from hub.experiments.signals import RECORDED_TOPICS, sample_rows
from hub.kit_study.robot_bridge import RobotBridge
from hub.kit_study.robotd.base import EmergencyStop, ProtectiveStop, RobotError, RobotFault
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


def until(pred, timeout=2.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


def test_estop_clears_queue_and_publishes():
    slow = SimBackend(timing={"home": 0.3, "pick": 0.3, "place": 0.3, "open_gripper": 0.3, "noise_std": 0.0},
                      rng=random.Random(0))
    bus2 = MessageBus(); ev2 = []
    bus2.subscribe("*", lambda m: ev2.append((m["topic"], m["data"])))
    b2 = RobotBridge(bus2, slow, monitor_interval=5.0); b2.start()
    for _ in range(5):
        b2.submit("home")
    time.sleep(0.05)
    dropped = b2.clear_queue()
    assert dropped >= 3 and b2.queue_size() == 0
    b2.submit("home"); b2.submit("home")
    b2.estop()
    assert b2.queue_size() == 0
    estops = [d for t, d in ev2 if t == "robot.estop"]
    assert estops and estops[-1] == {"reason": "estop", "source": "wizard"}
    b2.stop()


def test_estop_latches_until_home_and_rejects_everything_else():
    """C1: STOP must latch — no skill may sneak back onto the robot before a reset."""
    bridge, events, backend = make()
    bridge.estop()
    assert bridge.latched() == "estop"
    assert bridge.state()["latched"] == "estop"

    events.clear()
    assert bridge.supply("F1O1P1", "BL1", "L") is None
    assert bridge.submit("open_gripper") is None
    rejected = [d for t, d in events if t == "robot.rejected"]
    assert len(rejected) == 2
    assert rejected[0] == {"skill": "supply", "reason": "estop",
                           "args": {"part_id": "F1O1P1", "depot_slot": "BL1", "staging_slot": "L"}}
    assert "robot.skill_queued" not in topics(events)
    assert bridge.queue_size() == 0

    # home is the only accepted skill; it clears the latch
    events.clear()
    assert bridge.submit("home") is not None
    assert bridge.wait_idle(2.0)
    assert "robot.resumed" in topics(events)
    assert bridge.latched() is None

    events.clear()
    assert bridge.supply("F1O1P1", "BL1", "L") is not None
    assert bridge.wait_idle(2.0)
    assert "robot.part_staged" in topics(events)
    bridge.stop()


def test_stop_mid_skill_aborts_and_flags_aborted():
    """The sim must interrupt the running skill so an aborted motion is observable."""
    bus = MessageBus(); events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    backend = SimBackend(timing={"home": 0.5, "pick": 0.5, "place": 0.5, "open_gripper": 0.5,
                                 "noise_std": 0.0}, rng=random.Random(0))
    bridge = RobotBridge(bus, backend, monitor_interval=5.0)
    bridge.start()
    started = threading.Event()
    bus.subscribe("robot.skill_started", lambda m: started.set())
    bridge.supply("F1O1P1", "BL1", "L")
    assert started.wait(1.0)
    bridge.estop()
    assert bridge.wait_idle(1.5)
    failed = [d for t, d in events if t == "robot.skill_failed"]
    assert failed and failed[-1]["aborted"] is True and failed[-1]["protective_stop"] is False
    assert "robot.part_staged" not in topics(events)
    assert bridge.latched() == "estop"
    bridge.stop()


def test_protective_stop_latches_the_bridge():
    class PS(SimBackend):
        def pick(self, depot_slot):
            raise ProtectiveStop("protective stop")
    bus = MessageBus(); events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    bridge = RobotBridge(bus, PS(rng=random.Random(0)), monitor_interval=5.0)
    bridge.start()
    bridge.supply("P", "RD1", "C")
    assert bridge.wait_idle(2.0)
    assert bridge.latched() == "protective_stop"
    estops = [d for t, d in events if t == "robot.estop"]
    assert estops == [{"reason": "protective_stop", "source": "backend"}]
    assert bridge.supply("P2", "RD2", "L") is None
    bridge.stop()


def test_monitor_latches_on_safety_transition_while_idle():
    """C4: a protective stop while the robot waits must not go unnoticed."""
    class Watched(SimBackend):
        safety = "normal"
        def state(self):
            st = super().state()
            st.safety = self.safety
            return st

    bus = MessageBus(); estops = []
    bus.subscribe("robot.estop", lambda m: estops.append(m["data"]))
    backend = Watched(timing={"home": 0.01, "pick": 0.01, "place": 0.01, "open_gripper": 0.01,
                              "noise_std": 0.0}, rng=random.Random(0))
    bridge = RobotBridge(bus, backend, monitor_interval=0.02)
    bridge.start()
    assert bridge.latched() is None
    backend.safety = "protective_stop"
    assert until(lambda: bridge.latched() == "protective_stop", 1.0)
    assert estops == [{"reason": "protective_stop", "source": "monitor"}]
    assert bridge.state()["latched"] == "protective_stop"
    # the transition is reported once, not every poll
    time.sleep(0.1)
    assert len(estops) == 1
    bridge.stop()


def test_start_survives_unreachable_backend_and_connect_retries():
    """I1: an unreachable UR5 must not stop the app from starting."""
    calls = {"n": 0}
    class Flaky(SimBackend):
        def connect(self):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("no route to host")
            super().connect()

    bus = MessageBus(); states = []
    bus.subscribe("robot.state", lambda m: states.append(m["data"]))
    bridge = RobotBridge(bus, Flaky(timing={"home": 0.01, "pick": 0.01, "place": 0.01,
                                            "open_gripper": 0.01, "noise_std": 0.0},
                                    rng=random.Random(0)), monitor_interval=5.0)
    bridge.start()                                  # must not raise
    st = bridge.state()
    assert st["connected"] is False and st["safety"] == "disconnected" and st["latched"] is None
    assert states and states[-1]["safety"] == "disconnected"
    st = bridge.connect()
    assert st["connected"] is True and st["safety"] == "normal"
    assert bridge.submit("home") is not None and bridge.wait_idle(2.0)
    bridge.stop()


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
        [("robot.supply_duration_s", 4.2)]
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
    started = threading.Event()
    bus.subscribe("robot.skill_started", lambda m: started.set())
    bridge.submit("home")
    assert started.wait(2.0), "worker never dequeued the job"
    bridge.clear_queue()
    # queue is empty but job is still running
    assert bridge.wait_idle(0.05) is False
    backend._gate.set()  # release the blocking home
    assert bridge.wait_idle(1.0) is True
    bridge.stop()


def test_set_pace_is_admitted_through_the_latch():
    """N1: set_pace commands no motion, so a profile change must survive a latch — otherwise
    the robot runs at `normal` while the profile/CSV say `slow`."""
    bridge, events, backend = make()
    bridge.estop()
    assert bridge.latched() == "estop"

    events.clear()
    assert bridge.submit("set_pace", level="slow") is not None
    assert bridge.wait_idle(2.0)
    assert backend.state().pace == "slow"
    assert "robot.rejected" not in topics(events)
    # everything that *does* move is still refused
    assert bridge.supply("F1O1P1", "BL1", "L") is None
    assert bridge.latched() == "estop"
    bridge.stop()


def test_robot_fault_latches_like_a_protective_stop():
    """N2: a refused/failed move is a robot fault — latch, don't blame the part."""
    class Broken(SimBackend):
        def pick(self, depot_slot):
            raise RobotFault("moveJ refused")

    bus = MessageBus(); events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    bridge = RobotBridge(bus, Broken(rng=random.Random(0)), monitor_interval=5.0)
    bridge.start()
    bridge.supply("P", "RD1", "C")
    assert bridge.wait_idle(2.0)
    assert bridge.latched() == "robot_fault"
    failed = [d for t, d in events if t == "robot.skill_failed"]
    assert len(failed) == 1
    assert failed[0]["robot_fault"] is True and failed[0]["protective_stop"] is False
    assert failed[0]["safety"] == "robot_fault"
    estops = [d for t, d in events if t == "robot.estop"]
    assert estops[-1]["reason"] == "robot_fault" and estops[-1]["source"] == "backend"
    assert estops[-1]["error"] == "moveJ refused"
    assert bridge.supply("P2", "RD2", "L") is None
    bridge.stop()


def test_failure_while_disconnected_is_a_robot_fault():
    """N2(a): even a plain RobotError counts as a robot fault when the backend is down."""
    bus = MessageBus(); events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    backend = SimBackend(timing={"home": 0.01, "pick": 0.01, "place": 0.01,
                                 "open_gripper": 0.01, "noise_std": 0.0}, rng=random.Random(0))
    bridge = RobotBridge(bus, backend, monitor_interval=5.0)
    bridge.start()
    backend.disconnect()                     # SimBackend._run raises RobotError("not connected")
    bridge.supply("P", "RD1", "C")
    assert bridge.wait_idle(2.0)
    failed = [d for t, d in events if t == "robot.skill_failed"]
    assert failed and failed[-1]["robot_fault"] is True
    assert bridge.latched() == "robot_fault"
    bridge.stop()


def test_emergency_stop_and_protective_stop_map_to_different_reasons():
    """N3: PolyScope needs a reset for one and a re-power for the other."""
    def run(exc):
        class Backend(SimBackend):
            def pick(self, depot_slot):
                raise exc
        bus = MessageBus(); events = []
        bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
        bridge = RobotBridge(bus, Backend(rng=random.Random(0)), monitor_interval=5.0)
        bridge.start()
        bridge.supply("P", "RD1", "C")
        assert bridge.wait_idle(2.0)
        out = (bridge.latched(),
               [d for t, d in events if t == "robot.skill_failed"][-1],
               [d for t, d in events if t == "robot.estop"][-1])
        bridge.stop()
        return out

    latched, failed, estop = run(EmergencyStop("e-stop"))
    assert latched == "emergency_stop" and failed["safety"] == "emergency_stop"
    assert failed["protective_stop"] is True and failed["robot_fault"] is False
    assert estop == {"reason": "emergency_stop", "source": "backend"}

    latched, failed, estop = run(ProtectiveStop("protective stop"))
    assert latched == "protective_stop" and failed["safety"] == "protective_stop"
    assert estop == {"reason": "protective_stop", "source": "backend"}


def test_grasp_miss_is_not_a_robot_fault():
    class Miss(SimBackend):
        def pick(self, depot_slot):
            raise RobotError("simulated grasp failure")
    bus = MessageBus(); events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    bridge = RobotBridge(bus, Miss(rng=random.Random(0)), monitor_interval=5.0)
    bridge.start()
    bridge.supply("P", "RD1", "C")
    assert bridge.wait_idle(2.0)
    failed = [d for t, d in events if t == "robot.skill_failed"]
    assert failed[-1]["robot_fault"] is False and failed[-1]["safety"] is None
    assert bridge.latched() is None
    bridge.stop()


def test_estop_latches_before_it_clears_the_queue():
    """A submit racing STOP must be rejected, not land in the queue behind the drain."""
    box = {}

    class Racer(SimBackend):
        def stop(self):
            # runs from inside estop(), after clear_queue(): the latch must already hold
            box["job"] = bridge.submit("open_gripper")
            box["latched"] = bridge.latched()
            box["queue"] = bridge.queue_size()
            super().stop()

    bus = MessageBus(); events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    backend = Racer(timing={"home": 0.01, "pick": 0.01, "place": 0.01, "open_gripper": 0.01,
                            "noise_std": 0.0}, rng=random.Random(0))
    bridge = RobotBridge(bus, backend, monitor_interval=5.0)
    bridge.start()
    bridge.estop()
    assert box["latched"] == "estop"
    assert box["job"] is None and box["queue"] == 0
    assert bridge.queue_size() == 0
    assert [d for t, d in events if t == "robot.rejected"]
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
