import random
import time

import pytest

from hub.bus import MessageBus
from hub.kit_study.orders import load_block
from hub.kit_study.robot_bridge import RobotBridge
from hub.kit_study.robotd.sim import SimBackend
from hub.kit_study.supply import SupplyController, SupplyProfile
from hub.kit_study.task_engine import TaskEngine

F1 = "hub/kit_study/configs/orders_f1.yaml"
FAST = {"home": 0.005, "pick": 0.005, "place": 0.005, "open_gripper": 0.005, "noise_std": 0.0}


def stack(profile):
    bus = MessageBus()
    events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    block = load_block(F1)
    bridge = RobotBridge(bus, SimBackend(timing=FAST, rng=random.Random(0)))
    bridge.start()
    eng = TaskEngine(bus, block, rng=random.Random(0))
    ctrl = SupplyController(bus, bridge, block, profile)
    ctrl.start()
    return bus, events, eng, bridge, ctrl


def settle(bridge, ctrl, pred, timeout=2.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        bridge.wait_idle(0.05)
        if pred(ctrl.status()):
            return True
        time.sleep(0.01)
    return pred(ctrl.status())


def test_lookahead_two_prestages_two_parts_then_refills():
    bus, events, eng, bridge, ctrl = stack(SupplyProfile(lookahead=2, side="R"))
    eng.start_block()                                   # O1 has 4 parts
    assert settle(bridge, ctrl, lambda s: len(s["staged"]) == 2)
    st = ctrl.status()
    assert set(st["staged"].values()) == {"F1O1P1", "F1O1P2"}
    assert "R" in st["staged"]                           # preferred side used first
    eng.mark_part_placed()                              # participant takes P1
    assert settle(bridge, ctrl, lambda s: "F1O1P3" in s["staged"].values())
    bridge.stop(); ctrl.stop()


def test_lookahead_zero_waits_for_request():
    bus, events, eng, bridge, ctrl = stack(SupplyProfile(lookahead=0, side="C"))
    eng.start_block()
    bridge.wait_idle(0.5)
    assert ctrl.status()["staged"] == {}
    bus.publish("wizard.request_part", {})
    assert settle(bridge, ctrl, lambda s: s["staged"].get("C") == "F1O1P1")
    bridge.stop(); ctrl.stop()


def test_order_change_resets_mat_and_supplies_new_order():
    bus, events, eng, bridge, ctrl = stack(SupplyProfile(lookahead=1))
    eng.start_block()
    for _ in range(4):
        assert settle(bridge, ctrl, lambda s: len(s["staged"]) >= 1)
        eng.mark_part_placed()
    eng.next_order()                                     # O2
    assert settle(bridge, ctrl, lambda s: s["order_id"] == "O2" and "F1O2P1" in s["staged"].values())
    assert all(v.startswith("F1O2") for v in ctrl.status()["staged"].values())
    bridge.stop(); ctrl.stop()


def test_failed_supply_is_retried_once():
    bus = MessageBus()
    fails = {"n": 0}
    class Flaky(SimBackend):
        def pick(self, depot_slot):
            if fails["n"] == 0:
                fails["n"] += 1
                from hub.kit_study.robotd.base import RobotError
                raise RobotError("miss")
            return super().pick(depot_slot)
    block = load_block(F1)
    bridge = RobotBridge(bus, Flaky(timing=FAST, rng=random.Random(0))); bridge.start()
    eng = TaskEngine(bus, block, rng=random.Random(0))
    ctrl = SupplyController(bus, bridge, block, SupplyProfile(lookahead=1)); ctrl.start()
    eng.start_block()
    assert settle(bridge, ctrl, lambda s: "F1O1P1" in s["staged"].values())
    assert fails["n"] == 1
    bridge.stop(); ctrl.stop()


def test_profile_validation_and_set_profile():
    with pytest.raises(ValueError):
        SupplyProfile(lookahead=4)
    with pytest.raises(ValueError):
        SupplyProfile(side="X")
    bus, events, eng, bridge, ctrl = stack(SupplyProfile(lookahead=1))
    ctrl.set_profile(lookahead=3, side="L", pace="slow")
    assert ctrl.status()["profile"] == {"lookahead": 3, "side": "L", "pace": "slow", "announce": False}
    assert any(t == "supply.state" for t, _ in events)
    bridge.stop(); ctrl.stop()
