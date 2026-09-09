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


def test_twice_failed_part_goes_terminal_and_is_not_repicked():
    """F1: twice-failed parts are terminal and never repicked"""
    from hub.kit_study.robotd.base import RobotError
    bus = MessageBus()
    events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    fails = {"n": 0}
    class Flaky(SimBackend):
        def pick(self, depot_slot):
            # Fail only on first depot slot (BL1 = F1O1P1) twice, then succeed
            if depot_slot == "BL1" and fails["n"] < 2:
                fails["n"] += 1
                raise RobotError("miss")
            return super().pick(depot_slot)
    block = load_block(F1)
    bridge = RobotBridge(bus, Flaky(timing=FAST, rng=random.Random(0))); bridge.start()
    eng = TaskEngine(bus, block, rng=random.Random(0))
    ctrl = SupplyController(bus, bridge, block, SupplyProfile(lookahead=2)); ctrl.start()
    eng.start_block()
    # After first two failures, P1 should be terminal (not retried again)
    assert settle(bridge, ctrl, lambda s: "F1O1P1" in s["failed"], timeout=4.0)
    st = ctrl.status()
    assert st["failed"] == ["F1O1P1"]
    assert st["blocked"] is not None
    assert st["blocked"]["reason"] == "part_failed"
    # P2, P3 should be staged (other parts work)
    assert len(st["staged"]) > 0
    # Ensure P1 is current part, then request to clear failure
    bus.publish("task.step", {"step_index": 0, "part_id": "F1O1P1"})
    bridge.wait_idle(0.1)
    bus.publish("wizard.request_part", {})
    # Should now clear failure and succeed on next attempt
    assert settle(bridge, ctrl, lambda s: "F1O1P1" in s["staged"].values(), timeout=4.0)
    assert ctrl.status()["blocked"] is None
    # N3: check recovery decision reason is "request-current"
    recovery_decisions = [d for t, d in events if t == "supply.decision" and d.get("part_id") == "F1O1P1" and d.get("reason") == "request-current"]
    assert len(recovery_decisions) >= 1, "Recovery decision should have reason='request-current'"
    bridge.stop(); ctrl.stop()


def test_perturbation_swap_reprioritises_current_part():
    """F2: perturbation swaps _plan in sync with engine"""
    bus = MessageBus()
    events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    block = load_block(F1)
    bridge = RobotBridge(bus, SimBackend(timing=FAST, rng=random.Random(0)))
    bridge.start()
    ctrl = SupplyController(bus, bridge, block, SupplyProfile(lookahead=2))
    ctrl.start()

    # Publish synthetic engine events: order O6 (index 5)
    bus.publish("task.order_started", {"order_id": "O6", "order_index": 5, "kind": "block", "n_parts": 9, "time_limit_s": 120})
    bridge.wait_idle(0.1)

    # Start step 0, part F1O6P1
    bus.publish("task.step", {"step_index": 0, "part_id": "F1O6P1"})
    assert settle(bridge, ctrl, lambda s: any("F1O6P1" in str(v) for v in s["staged"].values()), timeout=2.0)

    # Verify plan before swap
    before_swap = list(p.id for p in ctrl._plan)  # Directly access _plan for verification

    # Swap indices 1 and 4: engine swaps its parts
    bus.publish("task.perturbation", {"swap": [1, 4]})
    bridge.wait_idle(0.1)

    # Verify controller's plan was swapped in sync
    after_swap = list(p.id for p in ctrl._plan)
    assert before_swap[1] == after_swap[4], "plan swap was not applied"
    assert before_swap[4] == after_swap[1], "plan swap was not applied"

    # Place P1
    bus.publish("task.part_placed", {"part_id": "F1O6P1"})
    bridge.wait_idle(0.1)

    # Move to step 1, part F1O6P5 (the swapped-in part at new index 1)
    bus.publish("task.step", {"step_index": 1, "part_id": "F1O6P5"})

    # Controller should track P5 as current part
    bridge.wait_idle(0.1)
    assert ctrl._current_part_id == "F1O6P5"
    bridge.stop(); ctrl.stop()


def test_mat_full_with_unstaged_current_part_reports_blocked_and_slot_cleared_recovers():
    """F2: mat_full blocked detection and slot_cleared recovery"""
    bus = MessageBus()
    events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    block = load_block(F1)
    bridge = RobotBridge(bus, SimBackend(timing=FAST, rng=random.Random(0)))
    bridge.start()
    ctrl = SupplyController(bus, bridge, block, SupplyProfile(lookahead=3))
    ctrl.start()

    # Start order O3 (index 2, 9 parts)
    bus.publish("task.order_started", {"order_id": "O3", "order_index": 2, "kind": "block", "n_parts": 9, "time_limit_s": 120})

    # Wait for 3 parts to stage (P1, P2, P3)
    assert settle(bridge, ctrl, lambda s: len(s["staged"]) == 3, timeout=2.0)
    st = ctrl.status()
    staged_parts = list(st["staged"].values())
    staged_slot = list(st["staged"].keys())[0]  # e.g., "L", "C", or "R"

    # Publish step making P9 current (simulating a swap or late step)
    bus.publish("task.step", {"step_index": 0, "part_id": "F1O3P9"})
    bridge.wait_idle(0.1)

    # P9 is current but all slots are full → blocked with reason "mat_full"
    assert settle(bridge, ctrl, lambda s: s["blocked"] is not None and s["blocked"]["reason"] == "mat_full", timeout=2.0)
    assert any(t == "supply.blocked" for t, _ in events)

    # Clear one slot (e.g., the one with P3)
    bus.publish("wizard.slot_cleared", {"slot": staged_slot})
    bridge.wait_idle(0.1)

    # P9 should now be staged, and blocked should be None
    assert settle(bridge, ctrl, lambda s: "F1O3P9" in s["staged"].values() and s["blocked"] is None, timeout=2.0)
    bridge.stop(); ctrl.stop()


def test_set_profile_does_not_hold_lock_while_submitting():
    """N2: set_profile does not deadlock by holding lock during bridge.submit"""
    import threading
    bus = MessageBus()
    callback_results = {"status_returned": False}

    def status_on_skill_queued(m):
        # N2: callback must call ctrl.status() to test the lock is released
        try:
            result = ctrl.status()
            callback_results["status_returned"] = result is not None
        except:
            pass

    block = load_block(F1)
    bridge = RobotBridge(bus, SimBackend(timing=FAST, rng=random.Random(0)))
    bridge.start()
    bus.subscribe("robot.skill_queued", status_on_skill_queued)
    ctrl = SupplyController(bus, bridge, block, SupplyProfile(lookahead=1))
    ctrl.start()

    # Run set_profile in a thread; if lock is held during bridge.submit, it will deadlock
    def set_prof():
        ctrl.set_profile(pace="slow")

    t = threading.Thread(target=set_prof)
    t.start()
    t.join(timeout=1.0)

    # N2: if thread is still alive, we deadlocked
    assert not t.is_alive(), "set_profile deadlocked (lock held during bridge.submit)"
    assert callback_results["status_returned"], "callback should have called ctrl.status() and returned"
    bridge.stop(); ctrl.stop()


def test_blocked_publish_does_not_hold_lock():
    """N2: supply.blocked publish does not hold lock during publish"""
    import threading
    bus = MessageBus()
    callback_results = {"status_returned": False}

    def status_on_blocked(m):
        # N2: blocked callback must call ctrl.status() to test the lock is released
        try:
            result = ctrl.status()
            callback_results["status_returned"] = result is not None
        except:
            pass

    block = load_block(F1)
    bridge = RobotBridge(bus, SimBackend(timing=FAST, rng=random.Random(0)))
    bridge.start()
    bus.subscribe("supply.blocked", status_on_blocked)
    ctrl = SupplyController(bus, bridge, block, SupplyProfile(lookahead=3))
    ctrl.start()

    # Trigger mat-full blocked scenario
    bus.publish("task.order_started", {"order_id": "O3", "order_index": 2, "kind": "block", "n_parts": 9, "time_limit_s": 120})
    assert settle(bridge, ctrl, lambda s: len(s["staged"]) == 3, timeout=2.0)

    # Publish step making P9 current with all slots full → blocked event
    bus.publish("task.step", {"step_index": 0, "part_id": "F1O3P9"})

    # Wait for blocked event to be published and callback to run
    assert settle(bridge, ctrl, lambda s: s["blocked"] is not None, timeout=2.0)
    bridge.wait_idle(0.2)

    # N2: callback should have run and called status() without deadlock
    assert callback_results["status_returned"], "blocked callback should have called ctrl.status() and returned"
    bridge.stop(); ctrl.stop()
