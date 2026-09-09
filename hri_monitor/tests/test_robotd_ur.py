"""URBackend over a fake RTDE stack that models ur_rtde's *asynchronous* move semantics.

The real interface: `moveJ(q, v, a, True)` returns a bool immediately, the move runs on the
controller, and `getAsyncOperationProgress()` reports >= 0 while it runs and a negative
value (toggling -1/-2) once it finishes. Only an async move can be interrupted by
stopJ/stopL — which is why URBackend polls instead of blocking.
"""
import threading

import pytest
import yaml

from hub.kit_study.robotd.base import Aborted, ProtectiveStop, RobotError
from hub.kit_study.robotd.ur import DEFAULT_SPEEDS, GRIPPER_TOOL_DO, URBackend, load_calibration

Q = [0.1, -1.5, 1.2, -1.3, -1.57, 0.0]
POSE = [0.4, -0.2, 0.15, 0.0, 3.14, 0.0]
CAL = {
    "robot_ip": "192.168.131.140", "approach_dz_m": 0.05,
    "home": {"q": Q}, "transit": {"q": Q},
    "depot": {"RD1": {"q": Q, "pose": POSE}},
    "staging": {"L": {"q": Q, "pose": POSE}, "C": {"q": Q, "pose": POSE}, "R": {"q": Q, "pose": POSE}},
}


class FakeRobot:
    """State shared by the three fake RTDE interfaces — one simulated controller."""

    def __init__(self, steps: int = 2):
        self.q = list(Q)
        self.pose = list(POSE)
        self.qd = [0.0] * 6
        self.ps = False
        self.es = False
        self.steps = steps          # progress values reported before the operation ends
        self.hold = False           # True: the async operation never finishes by itself
        self.reach = True           # False: finishing leaves the arm short of the target
        self.silent = False         # True: controller never reports progress for this move
        self.polls = 0
        self.on_poll = None         # hook(robot) run on every progress poll
        self._progress = -1
        self._last_neg = -1
        self._running = False
        self._target = None
        self._left = 0

    # ---------------------------------------------------------- control side
    def start(self, kind, target):
        self._running = True
        self._target = (kind, [float(x) for x in target])
        self._left = self.steps
        self.qd = [0.2] * 6
        if not self.silent:
            self._progress = 0

    def _finish(self, reached=None):
        if self._target is not None and (self.reach if reached is None else reached):
            kind, target = self._target
            if kind == "J":
                self.q = list(target)
            else:
                self.pose = list(target)
        self._running = False
        self.qd = [0.0] * 6
        if not self.silent:
            self._last_neg = -2 if self._last_neg == -1 else -1
            self._progress = self._last_neg

    def stop_motion(self):
        if self._running:
            self._finish(reached=False)

    # -------------------------------------------------------------- polling
    def poll(self) -> int:
        self.polls += 1
        if self.on_poll:
            self.on_poll(self)
        if self._running and not self.hold:
            if self._left <= 0:
                self._finish()
            else:
                self._left -= 1
                if not self.silent:
                    self._progress = self.steps - self._left
        return self._progress

    @property
    def running(self) -> bool:
        return self._running


class FakeAsyncStatus:
    """Mirrors rtde_control.AsyncOperationStatus."""

    def __init__(self, value: int):
        self._v = int(value)

    def isAsyncOperationRunning(self) -> bool:
        return self._v >= 0

    def value(self) -> int:
        return self._v


class FakeControl:
    def __init__(self, robot=None, with_ex=False):
        self.r = robot or FakeRobot()
        self.calls = []
        self.connected = True
        self.ik_result = None       # override the inverse-kinematics answer
        if with_ex:                 # only some builds expose the non-deprecated form
            self.getAsyncOperationProgressEx = self._progress_ex

    def isConnected(self): return self.connected
    def disconnect(self): self.connected = False

    def moveJ(self, q, speed=1.05, acceleration=1.4, asynchronous=False):
        self.calls.append(("moveJ", list(q), speed, acceleration, asynchronous))
        self.r.start("J", q)
        return True

    def moveL(self, pose, speed=0.25, acceleration=1.2, asynchronous=False):
        self.calls.append(("moveL", list(pose), speed, acceleration, asynchronous))
        self.r.start("L", pose)
        return True

    def getInverseKinematics(self, pose, qnear=None, max_position_error=1e-10,
                             max_orientation_error=1e-10):
        self.calls.append(("ik", list(pose)))
        if self.ik_result is not None:
            return list(self.ik_result)
        return [x + 0.01 for x in (qnear or Q)]

    def getAsyncOperationProgress(self) -> int:
        return self.r.poll()

    def _progress_ex(self):
        return FakeAsyncStatus(self.r.poll())

    def stopJ(self, a=2.0, asynchronous=False):
        self.calls.append(("stopJ", a)); self.r.stop_motion()

    def stopL(self, a=10.0, asynchronous=False):
        self.calls.append(("stopL", a)); self.r.stop_motion()

    def teachMode(self): self.calls.append(("teach",)); return True
    def endTeachMode(self): self.calls.append(("endteach",)); return True


class FakeReceive:
    def __init__(self, robot=None):
        self.r = robot or FakeRobot()

    @property
    def ps(self): return self.r.ps

    @ps.setter
    def ps(self, v): self.r.ps = v

    @property
    def es(self): return self.r.es

    @es.setter
    def es(self, v): self.r.es = v

    def isProtectiveStopped(self): return self.r.ps
    def isEmergencyStopped(self): return self.r.es
    def getSafetyMode(self): return 3 if self.r.ps else 1
    def getActualQ(self): return list(self.r.q)
    def getActualQd(self): return list(self.r.qd)
    def getActualTCPPose(self): return list(self.r.pose)


class FakeIO:
    def __init__(self): self.calls = []
    def setToolDigitalOut(self, out_id, level): self.calls.append((out_id, level)); return True


class NoCtrl:
    """Any attribute access is a bug: state()/stop() must not touch the control socket."""

    def __getattr__(self, name):
        raise AssertionError(f"control interface touched off the worker thread: ctrl.{name}")


def make(cal=CAL, with_ex=False, **kw):
    robot = FakeRobot()
    c, r, io = FakeControl(robot, with_ex=with_ex), FakeReceive(robot), FakeIO()
    kw.setdefault("gripper_settle_s", 0.0)
    kw.setdefault("poll_s", 0.0)
    b = URBackend("192.168.131.140", cal, rtde_factory=lambda ip: (c, r, io), **kw)
    b.connect()
    return b, c, r, io


# --------------------------------------------------------------- happy paths
def test_pick_sequence_and_gripper():
    b, c, r, io = make()
    b.pick("RD1")
    kinds = [k[0] for k in c.calls]
    assert kinds == ["moveJ", "ik", "moveJ", "moveL", "moveL"]
    assert io.calls == [(GRIPPER_TOOL_DO, True)]            # close
    assert c.calls[3][1][2] == pytest.approx(POSE[2])       # down to grasp height
    assert c.calls[4][1][2] == pytest.approx(POSE[2] + 0.05)  # retreat
    assert b.state().gripper_closed is True
    # every move was issued asynchronously, and its progress was polled
    assert all(k[4] is True for k in c.calls if k[0] in ("moveJ", "moveL"))
    assert c.r.polls >= 4
    assert b.state().busy is False and b.state().last_skill == "pick"


def test_progress_ex_variant_is_used_when_present():
    b, c, r, io = make(with_ex=True)
    b.home()
    assert c.r.polls >= 1
    assert b.state().last_skill == "home"


def test_move_without_progress_feedback_still_completes():
    """Some controllers report no progress for a short async move: fall back to
    'at the target and at rest'."""
    b, c, r, io = make()
    c.r.silent = True
    b.place("L")
    assert io.calls == [(GRIPPER_TOOL_DO, False)]


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


# ------------------------------------------------------------------- safety
def test_protective_stop_refuses_motion():
    b, c, r, io = make()
    r.ps = True
    with pytest.raises(ProtectiveStop):
        b.pick("RD1")
    assert c.calls == []
    assert b.state().safety == "protective_stop"


def test_protective_stop_after_move_completes_is_raised():
    """The move finishes but the controller latched a protective stop → ProtectiveStop."""
    b, c, r, io = make()

    def trip(rob):
        if rob.polls >= 2:
            rob.ps = True
    c.r.on_poll = trip
    with pytest.raises(ProtectiveStop):
        b.home()
    assert b.state().safety == "protective_stop"
    assert b.state().busy is False


def test_target_not_reached_raises():
    b, c, r, io = make(dict(CAL, home={"q": [x + 0.5 for x in Q]}), reach_grace_s=0.0)
    c.r.reach = False                      # the arm never arrives
    with pytest.raises(RobotError, match="target not reached"):
        b.home()
    assert [k[0] for k in c.calls] == ["moveJ"]


def test_move_timeout():
    b, c, r, io = make(poll_s=0.001, move_timeout_s=0.05)
    c.r.hold = True                        # the operation never finishes
    with pytest.raises(RobotError, match="move timeout"):
        b.home()


def test_mid_motion_protective_stop_is_classified():
    """A move the controller refuses while a protective stop is active is ProtectiveStop."""
    b, c, r, io = make()

    def moveL_then_stop(*a, **kw):
        c.r.ps = True
        return False
    c.moveL = moveL_then_stop
    with pytest.raises(ProtectiveStop, match="protective/emergency stop during motion"):
        b.pick("RD1")


def test_gripper_command_failure_raises_and_keeps_state():
    b, c, r, io = make()
    io.setToolDigitalOut = lambda out_id, level: False
    with pytest.raises(RobotError, match="gripper command refused"):
        b.pick("RD1")
    assert b.state().gripper_closed is False
    assert [k[0] for k in c.calls] == ["moveJ", "ik", "moveJ", "moveL"]  # no retreat


# ---------------------------------------------------------------------- stop
def test_stop_from_another_thread_aborts_the_move():
    b, c, r, io = make(poll_s=0.005)
    c.r.hold = True                        # the move stays "running" until stopJ
    moving = threading.Event()
    c.r.on_poll = lambda rob: moving.set()
    seen_busy = []

    def stopper():
        moving.wait(5.0)
        seen_busy.append(b.state().busy)   # state() from the API thread, mid-move
        b.stop()

    t = threading.Thread(target=stopper); t.start()
    with pytest.raises(Aborted):
        b.pick("RD1")
    t.join(5.0)

    assert seen_busy == [True]             # _busy reflects real motion
    assert ("stopJ", 2.0) in c.calls
    assert [k[0] for k in c.calls] == ["moveJ", "stopJ"]   # no further motion
    assert b.state().busy is False
    assert b.stop_latched is True

    # a latched stop refuses further motion without touching the robot
    before = len(c.calls)
    with pytest.raises(Aborted):
        b.pick("RD1")
    with pytest.raises(Aborted):
        b.open_gripper()
    assert len(c.calls) == before

    # home() is the resume path: it clears the latch and moves again
    c.r.hold = False
    c.r.on_poll = None
    b.home()
    assert b.stop_latched is False
    assert [k[0] for k in c.calls][before:] == ["moveJ"]


def test_stop_during_a_linear_move_uses_stopL():
    b, c, r, io = make(poll_s=0.005)
    moving = threading.Event()

    def hold_on_moveL(rob):
        if any(k[0] == "moveL" for k in c.calls):
            rob.hold = True
            moving.set()
    c.r.on_poll = hold_on_moveL
    t = threading.Thread(target=lambda: (moving.wait(5.0), b.stop()))
    t.start()
    with pytest.raises(Aborted):
        b.pick("RD1")
    t.join(5.0)
    assert ("stopL", 2.0) in c.calls
    assert not any(k[0] == "stopJ" for k in c.calls)


def test_stop_during_gripper_settle_aborts_before_retreat():
    b, c, r, io = make(gripper_settle_s=5.0)
    io.setToolDigitalOut = lambda out_id, level: (b.stop(), True)[1]
    with pytest.raises(Aborted):
        b.pick("RD1")
    assert [k[0] for k in c.calls] == ["moveJ", "ik", "moveJ", "moveL"]  # no retreat moveL


def test_stop_and_state_never_touch_the_control_interface():
    b, c, r, io = make()
    b.ctrl = NoCtrl()                      # any ctrl.<attr> access raises
    b.stop()                               # must only latch the flag
    st = b.state()
    assert st.connected is True and st.safety == "normal"
    assert b.stop_latched is True


def test_set_pace_is_allowed_while_stopped():
    b, c, r, io = make()
    b.stop()
    b.set_pace("slow")                     # no motion, so no abort
    assert b.state().pace == "slow"
    assert c.calls == []


# ------------------------------------------------------------------------ IK
@pytest.mark.parametrize("bad", [
    [],                                      # empty / no solution
    [0.0, 0.0, 0.0],                         # degenerate length
    [x + 1.4 for x in Q],                    # far branch (> 0.5 rad from the taught q)
    [float("nan")] * 6,                      # non-finite
])
def test_bad_ik_solution_is_rejected(bad):
    b, c, r, io = make()
    c.ik_result = bad
    with pytest.raises(RobotError, match="IK solution rejected for RD1"):
        b.pick("RD1")
    assert [k[0] for k in c.calls] == ["moveJ", "ik"]   # never moveJ onto a bad solution


# ------------------------------------------------------------------- plumbing
def test_unknown_slot():
    b, c, r, io = make()
    with pytest.raises(ValueError):
        b.pick("ZZ9")
    assert c.calls == []


def test_load_calibration_validates(tmp_path):
    p = tmp_path / "cal.yaml"
    p.write_text(yaml.safe_dump(CAL))
    cal = load_calibration(p)
    assert cal["staging"]["L"]["q"] == Q
    bad = dict(CAL); bad["staging"] = {"L": {"q": Q, "pose": POSE}}
    p.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError, match="staging"):
        load_calibration(p)


def test_disconnect_closes_all_interfaces_and_latches_abort():
    robot = FakeRobot()
    c, r, io = FakeControl(robot), FakeReceive(robot), FakeIO()
    r.disconnect = lambda: setattr(r, "disconnected", True)
    io.disconnect = lambda: setattr(io, "disconnected", True)
    b = URBackend("192.168.131.140", CAL, gripper_settle_s=0.0, poll_s=0.0,
                  rtde_factory=lambda ip: (c, r, io))
    b.connect()
    b.disconnect()
    assert c.connected is False
    assert getattr(r, "disconnected", False) and getattr(io, "disconnected", False)
    assert b.stop_latched is True
    st = b.state()
    assert st.connected is False and st.safety == "disconnected"


def test_state_on_disconnected_backend_does_not_raise():
    b = URBackend("192.168.131.140", CAL)
    st = b.state()
    assert st.connected is False and st.safety == "disconnected" and st.busy is False


def test_state_survives_a_dead_receive_interface():
    b, c, r, io = make()
    r.isEmergencyStopped = lambda: (_ for _ in ()).throw(RuntimeError("socket closed"))
    st = b.state()
    assert st.connected is False and st.safety == "disconnected"


# ---------------------------------------------------------------- teach_poses
def test_teach_record_builds_calibration():
    from hub.kit_study.robotd.teach_poses import record
    robot = FakeRobot()
    c, r = FakeControl(robot), FakeReceive(robot)
    cal = record(c, r, ["home", "transit", "L", "C", "R", "RD1"], prompt=lambda msg: "")
    assert set(cal["staging"]) == {"L", "C", "R"} and "RD1" in cal["depot"] and cal["home"]["q"] == Q
    assert [k[0] for k in c.calls].count("teach") == 6
    assert [k[0] for k in c.calls].count("endteach") == 6


def test_teach_record_ends_freedrive_on_keyboard_interrupt():
    from hub.kit_study.robotd.teach_poses import record
    robot = FakeRobot()
    c, r = FakeControl(robot), FakeReceive(robot)

    def boom(msg):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        record(c, r, ["home"], prompt=boom)
    assert [k[0] for k in c.calls] == ["teach", "endteach"]   # freedrive ended


def test_teach_main_ends_freedrive_and_disconnects_on_ctrl_c(tmp_path, capsys, monkeypatch):
    from hub.kit_study.robotd import teach_poses
    robot = FakeRobot()
    c, r = FakeControl(robot), FakeReceive(robot)
    r.disconnect = lambda: setattr(r, "disconnected", True)
    monkeypatch.setattr("builtins.input", lambda *a: (_ for _ in ()).throw(KeyboardInterrupt))
    out = tmp_path / "cal.yaml"
    rc = teach_poses.main(["--ip", "10.0.0.1", "--out", str(out), "--slots", "home"],
                          factory=lambda ip: (c, r))
    assert rc == 1
    assert [k[0] for k in c.calls] == ["teach", "endteach"]
    assert c.connected is False and getattr(r, "disconnected", False)
    assert not out.exists()                                   # nothing written
    assert "freedrive ended" in capsys.readouterr().out


def test_teach_main_writes_calibration(tmp_path, monkeypatch):
    from hub.kit_study.robotd.teach_poses import main
    robot = FakeRobot()
    c, r = FakeControl(robot), FakeReceive(robot)
    monkeypatch.setattr("builtins.input", lambda *a: "")
    out = tmp_path / "cal.yaml"
    rc = main(["--ip", "10.0.0.1", "--out", str(out), "--slots", "home", "transit", "L", "C", "R",
               "RD1"], factory=lambda ip: (c, r))
    assert rc == 0
    cal = yaml.safe_load(out.read_text())
    assert cal["robot_ip"] == "10.0.0.1" and "RD1" in cal["depot"]
    assert c.connected is False                               # interfaces closed
