"""Opt-in: exercises URBackend against a running URSim (or the real UR5).
    URSIM_IP=127.0.0.1 .venv/bin/pytest tests/test_ursim_optional.py -q
Requires the URSim program to be in Remote Control / a running program that allows RTDE control.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("URSIM_IP"), reason="set URSIM_IP to run")


def test_connect_home_and_gripper():
    from hub.kit_study.robotd.ur import URBackend, load_calibration
    cal = load_calibration("hub/kit_study/configs/calibration.example.yaml")
    b = URBackend(os.environ["URSIM_IP"], cal, gripper_settle_s=0.2)
    b.connect()
    try:
        assert b.state().connected
        b.home()
        b.open_gripper()
        assert b.state().last_skill == "open_gripper"
    finally:
        b.disconnect()
