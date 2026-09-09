"""Opt-in: exercises URBackend against a running URSim (or the real UR5).
    URSIM_IP=127.0.0.1 .venv/bin/pytest tests/test_ursim_optional.py -q
Requires the URSim program to be in Remote Control / a running program that allows RTDE control.
"""
import os
import threading

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("URSIM_IP"), reason="set URSIM_IP to run")


def _calibration():
    from hub.kit_study.robotd.ur import load_calibration
    return load_calibration("hub/kit_study/configs/calibration.example.yaml")


def _backend(**kw):
    from hub.kit_study.robotd.ur import URBackend
    kw.setdefault("gripper_settle_s", 0.2)
    return URBackend(os.environ["URSIM_IP"], _calibration(), **kw)


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
    cal = _calibration()
    b.connect()
    try:
        b.home()                      # start from a known pose
        # Park far from home (staging L is ~2.5 rad away): homing *from* the home pose is a
        # zero-length move that finishes before stop() can land, so the abort would never be
        # exercised. These two are synchronous helper moves, not URBackend skills.
        b.ctrl.moveJ(cal["transit"]["q"], 0.6, 0.8)
        b.ctrl.moveJ(cal["staging"]["L"]["q"], 0.6, 0.8)
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
