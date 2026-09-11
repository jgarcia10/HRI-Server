import random

import pytest

from hub.kit_study.robotd.base import PACE_FACTOR, RobotError, RobotState
from hub.kit_study.robotd.sim import SimBackend


class Sleeper:
    def __init__(self):
        self.total = 0.0
    def __call__(self, s):
        self.total += s


def make(**kw):
    sl = Sleeper()
    b = SimBackend(rng=random.Random(1), sleep=sl, **kw)
    b.connect()
    return b, sl


def test_state_and_connect():
    b, _ = make()
    st = b.state()
    assert isinstance(st, RobotState)
    assert st.connected and st.backend == "sim" and st.safety == "normal"
    assert st.as_dict()["gripper_closed"] is False


def test_pick_place_cycle_timing_and_gripper():
    b, sl = make(timing={"home": 1.0, "pick": 2.0, "place": 2.0, "open_gripper": 0.5, "noise_std": 0.0})
    b.pick("RD1")
    assert b.state().gripper_closed is True and b.state().last_skill == "pick"
    b.place("L")
    assert b.state().gripper_closed is False and b.state().last_skill == "place"
    assert abs(sl.total - 4.0) < 1e-9


def test_pace_scales_duration():
    b, sl = make(timing={"home": 1.0, "pick": 2.0, "place": 2.0, "open_gripper": 0.5, "noise_std": 0.0})
    b.set_pace("slow")
    b.pick("RD1")
    assert abs(sl.total - 2.0 * PACE_FACTOR["slow"]) < 1e-9
    with pytest.raises(ValueError):
        b.set_pace("ludicrous")


def test_slot_validation():
    b, _ = make()
    with pytest.raises(ValueError):
        b.place("X")
    with pytest.raises(ValueError):
        b.pick("not-a-slot")


def test_failure_rate_raises_robot_error():
    b, _ = make(failure_rate=1.0)
    with pytest.raises(RobotError):
        b.pick("RD1")
    assert b.state().gripper_closed is False


def test_stop_marks_not_busy_and_disconnect():
    b, _ = make()
    b.stop()
    assert b.state().busy is False
    b.disconnect()
    assert b.state().connected is False and b.state().safety == "disconnected"


def test_close_gripper_closes_and_reset_gripper_ends_open():
    b, sl = make(timing={"close_gripper": 1.0, "reset_gripper": 3.0, "noise_std": 0.0})
    b.close_gripper()
    assert b.state().gripper_closed is True and b.state().last_skill == "close_gripper"
    b.reset_gripper()
    assert b.state().gripper_closed is False and b.state().last_skill == "reset_gripper"
    assert abs(sl.total - 4.0) < 1e-9
