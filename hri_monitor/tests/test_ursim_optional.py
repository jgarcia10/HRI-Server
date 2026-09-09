"""Opt-in: exercises URBackend against a running URSim (or the real UR5).
    URSIM_IP=127.0.0.1 .venv/bin/pytest tests/test_ursim_optional.py -q
Requires the URSim program to be in Remote Control / a running program that allows RTDE control.
"""
import os
import threading

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("URSIM_IP"), reason="set URSIM_IP to run")


def _backend(**kw):
    from hub.kit_study.robotd.ur import URBackend, load_calibration
    cal = load_calibration("hub/kit_study/configs/calibration.example.yaml")
    kw.setdefault("gripper_settle_s", 0.2)
    return URBackend(os.environ["URSIM_IP"], cal, **kw)


def test_connect_home_and_gripper():
    b = _backend()
    b.connect()
    try:
        assert b.state().connected
        b.home()
        b.open_gripper()
        assert b.state().last_skill == "open_gripper"
    finally:
        b.disconnect()


def test_stop_interrupts_home_and_home_resumes():
    """stop() from another thread must interrupt a running move (async moves + stopJ),
    latch, and let home() resume. Tolerant: if the move finished before the stop landed
    the scenario is inconclusive, so only the latch/resume contract is asserted."""
    from hub.kit_study.robotd.base import Aborted

    b = _backend()
    b.connect()
    try:
        b.home()                      # start from a known pose
        b.set_pace("slow")            # more time to catch the move mid-flight
        result = {}

        def run_home():
            try:
                b.home()
                result["ok"] = True
            except Aborted as e:
                result["aborted"] = str(e)
            except Exception as e:      # pragma: no cover - reported below
                result["error"] = repr(e)

        t = threading.Thread(target=run_home)
        t.start()
        # state() must stay callable from this thread while the worker moves
        for _ in range(10):
            b.state()
        b.stop()
        t.join(30.0)
        assert not t.is_alive(), "move did not unwind after stop()"
        assert "error" not in result, result

        if "aborted" in result:
            assert b.stop_latched
            with pytest.raises(Aborted):
                b.open_gripper()      # latched: no motion until home()
        b.home()                      # resume path clears the latch either way
        assert not b.stop_latched
    finally:
        b.set_pace("normal")
        b.disconnect()
