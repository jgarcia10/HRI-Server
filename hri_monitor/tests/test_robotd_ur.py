import pytest
import yaml

from hub.kit_study.robotd.base import ProtectiveStop
from hub.kit_study.robotd.ur import DEFAULT_SPEEDS, GRIPPER_TOOL_DO, URBackend, load_calibration

Q = [0.1, -1.5, 1.2, -1.3, -1.57, 0.0]
POSE = [0.4, -0.2, 0.15, 0.0, 3.14, 0.0]
CAL = {
    "robot_ip": "192.168.131.140", "approach_dz_m": 0.05,
    "home": {"q": Q}, "transit": {"q": Q},
    "depot": {"RD1": {"q": Q, "pose": POSE}},
    "staging": {"L": {"q": Q, "pose": POSE}, "C": {"q": Q, "pose": POSE}, "R": {"q": Q, "pose": POSE}},
}


class FakeControl:
    def __init__(self):
        self.calls = []
        self.connected = True
    def isConnected(self): return self.connected
    def disconnect(self): self.connected = False
    def moveJ(self, q, speed=1.05, acceleration=1.4, asynchronous=False):
        self.calls.append(("moveJ", list(q), speed, acceleration)); return True
    def moveL(self, pose, speed=0.25, acceleration=1.2, asynchronous=False):
        self.calls.append(("moveL", list(pose), speed, acceleration)); return True
    def getInverseKinematics(self, pose, qnear=None, max_position_error=1e-10, max_orientation_error=1e-10):
        self.calls.append(("ik", list(pose))); return [x + 0.01 for x in (qnear or Q)]
    def stopJ(self, a=2.0): self.calls.append(("stopJ", a))
    def teachMode(self): self.calls.append(("teach",)); return True
    def endTeachMode(self): self.calls.append(("endteach",)); return True


class FakeReceive:
    def __init__(self): self.ps = False; self.es = False
    def isProtectiveStopped(self): return self.ps
    def isEmergencyStopped(self): return self.es
    def getSafetyMode(self): return 3 if self.ps else 1
    def getActualQ(self): return list(Q)
    def getActualTCPPose(self): return list(POSE)


class FakeIO:
    def __init__(self): self.calls = []
    def setToolDigitalOut(self, out_id, level): self.calls.append((out_id, level)); return True


def make(cal=CAL):
    c, r, io = FakeControl(), FakeReceive(), FakeIO()
    b = URBackend("192.168.131.140", cal, gripper_settle_s=0.0, rtde_factory=lambda ip: (c, r, io))
    b.connect()
    return b, c, r, io


def test_pick_sequence_and_gripper():
    b, c, r, io = make()
    b.pick("RD1")
    kinds = [k[0] for k in c.calls]
    assert kinds == ["moveJ", "ik", "moveJ", "moveL", "moveL"]
    assert io.calls == [(GRIPPER_TOOL_DO, True)]            # close
    assert c.calls[3][1][2] == pytest.approx(POSE[2])       # down to grasp height
    assert c.calls[4][1][2] == pytest.approx(POSE[2] + 0.05)  # retreat
    assert b.state().gripper_closed is True


def test_place_opens_gripper():
    b, c, r, io = make()
    b.place("L")
    assert io.calls == [(GRIPPER_TOOL_DO, False)]
    assert b.state().gripper_closed is False


def test_pace_selects_speeds():
    b, c, r, io = make()
    b.set_pace("slow")
    b.home()
    assert c.calls[-1][2] == DEFAULT_SPEEDS["slow"]["joint_v"]
    b.set_pace("normal"); b.home()
    assert c.calls[-1][2] == DEFAULT_SPEEDS["normal"]["joint_v"]


def test_protective_stop_refuses_motion():
    b, c, r, io = make()
    r.ps = True
    with pytest.raises(ProtectiveStop):
        b.pick("RD1")
    assert c.calls == []
    assert b.state().safety == "protective_stop"


def test_unknown_slot_and_stop():
    b, c, r, io = make()
    with pytest.raises(ValueError):
        b.pick("ZZ9")
    b.stop()
    assert ("stopJ", 2.0) in c.calls


def test_load_calibration_validates(tmp_path):
    p = tmp_path / "cal.yaml"
    p.write_text(yaml.safe_dump(CAL))
    cal = load_calibration(p)
    assert cal["staging"]["L"]["q"] == Q
    bad = dict(CAL); bad["staging"] = {"L": {"q": Q, "pose": POSE}}
    p.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError, match="staging"):
        load_calibration(p)


def test_teach_record_builds_calibration():
    from hub.kit_study.robotd.teach_poses import record
    c, r = FakeControl(), FakeReceive()
    cal = record(c, r, ["home", "transit", "L", "C", "R", "RD1"], prompt=lambda msg: "")
    assert set(cal["staging"]) == {"L", "C", "R"} and "RD1" in cal["depot"] and cal["home"]["q"] == Q
    assert [k[0] for k in c.calls].count("teach") == 6


def test_gripper_command_failure_raises_and_keeps_state():
    """Gripper command that returns False raises RobotError and keeps state unchanged."""
    from hub.kit_study.robotd.base import RobotError
    c, r = FakeControl(), FakeReceive()
    io = FakeIO()
    io.setToolDigitalOut = lambda out_id, level: False  # simulate gripper failure
    b = URBackend("192.168.131.140", CAL, gripper_settle_s=0.0, rtde_factory=lambda ip: (c, r, io))
    b.connect()
    with pytest.raises(RobotError, match="gripper command refused"):
        b.pick("RD1")
    assert b.state().gripper_closed is False  # state unchanged
    # No retreat moveL after gripper failure
    kinds = [k[0] for k in c.calls]
    assert kinds == ["moveJ", "ik", "moveJ", "moveL"]  # stops after down moveL


def test_mid_motion_protective_stop_is_classified():
    """Motion that fails with protective stop active is classified as ProtectiveStop."""
    c, r = FakeControl(), FakeReceive()
    io = FakeIO()
    # Make moveL fail and set protective stop after the check
    original_moveL = c.moveL
    def moveL_then_stop(*args, **kwargs):
        r.ps = True  # protective stop activates during motion
        return False  # motion fails
    c.moveL = moveL_then_stop
    b = URBackend("192.168.131.140", CAL, gripper_settle_s=0.0, rtde_factory=lambda ip: (c, r, io))
    b.connect()
    with pytest.raises(ProtectiveStop, match="protective/emergency stop during motion"):
        b.pick("RD1")


def test_disconnect_closes_all_interfaces():
    """disconnect() calls disconnect on all three interfaces (if they have it)."""
    class TrackingControl(FakeControl):
        def __init__(self):
            super().__init__()
            self.disconnect_called = False
        def disconnect(self):
            self.disconnect_called = True
            super().disconnect()
    class TrackingReceive(FakeReceive):
        def __init__(self):
            super().__init__()
            self.disconnect_called = False
        def disconnect(self):
            self.disconnect_called = True
    class TrackingIO(FakeIO):
        def __init__(self):
            super().__init__()
            self.disconnect_called = False
        def disconnect(self):
            self.disconnect_called = True
    c, r, io = TrackingControl(), TrackingReceive(), TrackingIO()
    b = URBackend("192.168.131.140", CAL, gripper_settle_s=0.0, rtde_factory=lambda ip: (c, r, io))
    b.connect()
    b.disconnect()
    assert c.disconnect_called and r.disconnect_called and io.disconnect_called
    assert b.state().safety == "disconnected"
