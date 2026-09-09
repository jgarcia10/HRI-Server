"""Fix round 3 (scoped re-review): raw RTDE exceptions latch when the backend is gone, and a
blocked-reason change while paused still reaches supply.blocked (and so the CSV marker)."""
import random
import time

from hub.bus import MessageBus
from hub.kit_study.orders import load_block
from hub.kit_study.robot_bridge import RobotBridge
from hub.kit_study.robotd.sim import SimBackend
from hub.kit_study.supply import SupplyController, SupplyProfile

F1 = "hub/kit_study/configs/orders_f1.yaml"
FAST = {"home": 0.005, "pick": 0.005, "place": 0.005, "open_gripper": 0.005, "noise_std": 0.0}


def until(pred, timeout=2.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


class SocketDrops(SimBackend):
    """First pick raises a raw RuntimeError (what ur_rtde throws when the control script dies)
    and the backend reports itself disconnected from then on — like a pulled cable mid-move."""

    def pick(self, depot_slot):
        self._connected = False
        raise RuntimeError("RTDE control script is not running!")


def test_raw_exception_while_disconnected_latches_as_robot_fault():
    bus = MessageBus(); events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    bridge = RobotBridge(bus, SocketDrops(timing=FAST, rng=random.Random(0)), monitor_interval=5.0)
    bridge.start()
    try:
        bridge.supply("F1O1P1", "BL1", "C")
        assert until(lambda: bridge.latched() == "robot_fault")
        failed = [d for t, d in events if t == "robot.skill_failed"]
        assert failed and failed[-1]["robot_fault"] is True and "RuntimeError" in failed[-1]["error"]
        estops = [d for t, d in events if t == "robot.estop"]
        assert estops and estops[-1]["reason"] == "robot_fault"
        # latched: the next supply is refused, not executed
        assert bridge.supply("F1O1P2", "BL2", "L") is None
    finally:
        bridge.stop()


def test_blocked_reason_change_while_paused_is_published():
    """Circuit-breaker path: P1 misses twice (blocked part_failed, published), then P2 misses →
    two consecutive failures on different parts latch robot_fault. The reason change must be
    published on supply.blocked too, or the CSV marker keeps saying part_failed."""
    bus = MessageBus(); events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    block = load_block(F1)
    bridge = RobotBridge(bus, SimBackend(timing=FAST, rng=random.Random(0)), monitor_interval=5.0)
    ctrl = SupplyController(bus, bridge, block, SupplyProfile(lookahead=1, side="C"))
    ctrl.start()
    try:
        bus.publish("task.order_started", {"order_id": "O1", "order_index": 0, "kind": "block",
                                           "n_parts": 4, "time_limit_s": 120})
        # State the breaker leaves behind: already blocked+published as part_failed, and the
        # pause reason pre-set to robot_fault before the latch (so the robot.estop dedup fires).
        with ctrl._lock:
            ctrl._paused = True; ctrl._pause_reason = "robot_fault"
            ctrl._blocked = {"reason": "part_failed", "needed": "F1O1P1", "staged": {}}
            ctrl._blocked_published = True
        events.clear()
        ctrl._replenish()
        reasons = [d["reason"] for t, d in events if t == "supply.blocked"]
        assert reasons == ["robot_fault"], reasons
        assert ctrl.status()["blocked"]["reason"] == "robot_fault"
        # unchanged reason → no duplicate
        events.clear(); ctrl._replenish()
        assert not [d for t, d in events if t == "supply.blocked"]
    finally:
        ctrl.stop()
