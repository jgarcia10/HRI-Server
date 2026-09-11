"""UR5 backend over ur_rtde. Fixed taught waypoints; no planning; PolyScope safety is authoritative.

Threading contract (important — the bridge runs skills on a worker thread while the API
thread serves /robot/stop and a ~3 Hz state monitor):

* Every `RTDEControlInterface` (``self.ctrl``) call happens on the thread that runs the
  skill — never anywhere else.  The one exception is :meth:`disconnect`, which is a
  shutdown path.
* Moves are issued **asynchronously** (``moveJ(q, v, a, True)``).  ur_rtde:
  "If async is true it is possible to stop a move command using either the stopJ or stopL
  function.  Default is false, this means the function will block until the movement has
  completed."  A blocking move cannot be interrupted, so `stop()` would be a no-op for up
  to a whole cycle and two threads would write the same control socket.
* :meth:`stop` therefore only latches ``self._abort`` (a ``threading.Event``).  The worker
  sees it on its next 50 ms poll and calls ``stopJ``/``stopL`` itself, then raises
  :class:`Aborted`.  The latch is cleared by :meth:`home` (the resume path) or
  :meth:`connect`.
* :meth:`state` reads only the receive interface and local flags, so it is cheap and safe
  to call from another thread while a move is running.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from pathlib import Path
from typing import Callable

import yaml

log = logging.getLogger(__name__)


from .base import (Aborted, EmergencyStop, RobotBackend, RobotError, RobotFault, ProtectiveStop,
                   RobotState, STAGING_SLOTS,
                   validate_depot_slot, validate_pace, validate_staging_slot)
from .gripper import Gripper, OnRobotURCapGripper, ToolDOGripper


class _IKCallFailed(RobotError):
    """The controller's IK *call* failed (as opposed to answering off-branch).

    On this cell at least one taught pose makes the controller's `getInverseKinematics`
    kill the running RTDE control script, so the script has to be reuploaded before any
    further motion is attempted."""


GRIPPER_TOOL_DO = 0          # tool digital output 0 == legacy SetIO(fun=1, pin=16); True = close
# Joint/linear speed and acceleration per pace level. Overridable from the mode config
# (`robot.speeds`) so the cell can be tuned without a code change. `fast` is roughly a third
# of the UR5's maximum joint speed (3.14 rad/s) — brisk next to a seated participant, with
# acceleration kept well below the arm's limit so the motion still reads as deliberate.
DEFAULT_SPEEDS = {
    "slow":   {"joint_v": 0.30, "joint_a": 0.50, "lin_v": 0.08, "lin_a": 0.30},
    "normal": {"joint_v": 0.60, "joint_a": 0.80, "lin_v": 0.15, "lin_a": 0.50},
    "fast":   {"joint_v": 1.10, "joint_a": 1.50, "lin_v": 0.30, "lin_a": 0.90},
}

# Verified fault-recovery sequence (measured 2026-09-11) for a gripper that latched a fault by
# closing fully on air: power-cycle the tool voltage, then wake it with a short DO0 pulse.
# Tool DO1 is never touched by this sequence (see ToolDOGripper / DualDOGripper docstrings).
GRIPPER_RESET_SCRIPT_NAME = "kit_tool_power"
GRIPPER_RESET_SCRIPT = (
    "  set_tool_voltage(0)\n"
    "  sleep(20)\n"
    "  set_tool_voltage(24)\n"
    "  sleep(2)\n"
)
GRIPPER_RESET_VOLTAGE_CYCLE_S = 22.0    # matches the script's own sleep(20) + sleep(2)
GRIPPER_RESET_WAKE_WAIT_S = 8.0         # gripper stays dark (tool AI0 ~0.07 V) after 24 V returns
GRIPPER_RESET_PULSE_S = 0.35            # short DO0-high pulse that wakes the gripper
GRIPPER_RESET_REUPLOAD_SETTLE_S = 0.2   # let the controller drop the temp script first
                                         # (same pattern as OnRobotURCapGripper.REUPLOAD_SETTLE_S)

POLL_S = 0.05                # async-progress poll period
MOVE_TIMEOUT_S = 20.0        # a taught move never takes this long; longer == something is wrong
STOP_TIMEOUT_S = 3.0         # bounded wait for the controller to report the stop took effect
REACH_GRACE_S = 0.3          # allow the arm to settle before declaring "target not reached"
Q_TOL_RAD = 0.02             # per-joint tolerance for "moveJ reached its target"
P_TOL_M = 0.003              # TCP position tolerance for "moveL reached its target"
# The guard exists to catch a *branch flip* (elbow up/down, wrist ±pi) — those are ~pi apart.
# It must not reject a legitimate solution: measured on the lab cell, the depot poses sit at
# sigma_min ~0.086, so the 3 cm vertical approach legitimately costs up to ~35 deg of joint
# travel there. 0.5 rad rejected most of them; 1.2 rad still leaves a wide margin below pi.
IK_BRANCH_TOL_RAD = 1.2      # IK result must stay on the taught branch
AT_REST_QD = 0.01            # rad/s below which the arm counts as stopped
STOP_DECEL = 2.0             # stopJ/stopL deceleration


def _default_factory(ip: str):
    import rtde_control, rtde_io, rtde_receive  # lazy: only robot mode needs the lib
    return (rtde_control.RTDEControlInterface(ip), rtde_receive.RTDEReceiveInterface(ip),
            rtde_io.RTDEIOInterface(ip))


def load_calibration(path) -> dict:
    cal = yaml.safe_load(Path(path).read_text())
    def q6(node, where):
        q = (node or {}).get("q")
        if not (isinstance(q, list) and len(q) == 6):
            raise ValueError(f"{where}: need q with 6 joint values")
    q6(cal.get("home"), "home"); q6(cal.get("transit"), "transit")
    for s in STAGING_SLOTS:
        if s not in cal.get("staging", {}):
            raise ValueError(f"staging: slot {s} missing")
        q6(cal["staging"][s], f"staging.{s}")
        if len(cal["staging"][s].get("pose", [])) != 6:
            raise ValueError(f"staging.{s}: need pose with 6 values")
    for name, node in cal.get("depot", {}).items():
        validate_depot_slot(name); q6(node, f"depot.{name}")
        if len(node.get("pose", [])) != 6:
            raise ValueError(f"depot.{name}: need pose with 6 values")
    cal.setdefault("approach_dz_m", 0.05)
    return cal


class URBackend(RobotBackend):
    name = "ur5"

    def __init__(self, ip: str, calibration: dict, speeds: dict | None = None,
                 gripper_settle_s: float = 1.0, gripper_open_settle_s: float | None = None,
                 rtde_factory=None,
                 gripper: Gripper | Callable | None = None, gripper_close_high: bool = True,
                 poll_s: float = POLL_S, move_timeout_s: float = MOVE_TIMEOUT_S,
                 stop_timeout_s: float = STOP_TIMEOUT_S, reach_grace_s: float = REACH_GRACE_S,
                 clock=time.monotonic,
                 gripper_reset_voltage_cycle_s: float = GRIPPER_RESET_VOLTAGE_CYCLE_S,
                 gripper_reset_wake_wait_s: float = GRIPPER_RESET_WAKE_WAIT_S,
                 gripper_reset_pulse_s: float = GRIPPER_RESET_PULSE_S,
                 gripper_reset_reupload_settle_s: float = GRIPPER_RESET_REUPLOAD_SETTLE_S):
        self.ip = ip
        self.cal = calibration
        # Merged per level, so a config that only retunes `fast` keeps the other two.
        self.speeds = {lvl: {**vals, **(speeds or {}).get(lvl, {})}
                       for lvl, vals in DEFAULT_SPEEDS.items()}
        # Closing starts from fully open (~110 mm) and the jaws travel the whole stroke in
        # ~7 s, so reaching a 32 mm brick needs ~6-8 s; opening only has to clear the brick,
        # which is a second or two. One wait for each, so releasing does not cost a close.
        self.settle = float(gripper_settle_s)
        self.open_settle = float(gripper_open_settle_s if gripper_open_settle_s is not None
                                 else gripper_settle_s)
        self._factory = rtde_factory or _default_factory
        # `settle_s=0.0`: URBackend does its own *interruptible* settle wait (see
        # _approach_and/open_gripper) so the default gripper must not sleep twice.
        # `gripper_close_high=False`: the lab RG2 v2 closes on DO0 = 0 and opens on DO0 = 1.
        #
        # `gripper` is either a ready Gripper instance (the common case — onrobot_modbus/
        # onrobot_urcap are self-contained network clients, and tests pass fakes), a *factory*
        # callable(io_getter, recv_getter=None) -> Gripper for the kinds that must bind to this
        # backend's own (reconnect-replaceable) RTDE interfaces — `runtime.build_gripper` hands
        # back one of those for `kind: dual_do` — or None, meaning "build the legacy default".
        if gripper is None:
            self.gripper = ToolDOGripper(io_getter=lambda: self.io, do=GRIPPER_TOOL_DO,
                                          settle_s=0.0, close_high=gripper_close_high)
        elif callable(gripper):
            self.gripper = gripper(lambda: self.io, recv_getter=lambda: self.recv)
        else:
            self.gripper = gripper
        self.poll_s = float(poll_s)
        self.move_timeout_s = float(move_timeout_s)
        self.stop_timeout_s = float(stop_timeout_s)
        self.reach_grace_s = float(reach_grace_s)
        # Reset-gripper timings are instance attributes (not bare module constants) so tests
        # can drive the whole ~30 s recovery sequence in milliseconds without touching its logic.
        self.gripper_reset_voltage_cycle_s = float(gripper_reset_voltage_cycle_s)
        self.gripper_reset_wake_wait_s = float(gripper_reset_wake_wait_s)
        self.gripper_reset_pulse_s = float(gripper_reset_pulse_s)
        self.gripper_reset_reupload_settle_s = float(gripper_reset_reupload_settle_s)
        self._clock = clock
        self.ctrl = self.recv = self.io = None
        self._pace = "normal"
        self._busy = False
        self._last = None
        self._abort = threading.Event()   # set by stop() (any thread), acted on by the worker

    # -------------------------------------------------------------- lifecycle
    def connect(self) -> None:
        """(Re)open the three RTDE interfaces.

        Two guards (fix round 2):
        * A reconnect clears the stop latch, so it must never be a back door around a STOP
          that a worker thread is still unwinding — refuse while a skill is running under a
          latched abort. `home` is the resume path, not `connect`.
        * Interfaces from a previous connect are closed first; otherwise a retry after a
          half-open connection leaks the old sockets and the RTDE control script keeps
          owning the robot.
        """
        if self._busy:
            # Closing the interfaces under a running skill would null ctrl/recv on the
            # worker thread; the wizard must STOP (and Home) before reconnecting.
            raise RobotError("skill in progress; stop the robot before reconnecting")
        self._close_interfaces()
        try:
            self.ctrl, self.recv, self.io = self._factory(self.ip)
        except Exception as e:
            raise RobotError(f"cannot connect to UR at {self.ip}: {e}") from e
        self.gripper.connect()
        if isinstance(self.gripper, OnRobotURCapGripper) and self.gripper.reupload is None:
            # Sending the URCap program over the secondary interface kills the ur_rtde control
            # script; reupload() restores it. `self.ctrl` is read lazily (not captured here) so
            # this keeps working across reconnects, and guards None so a call that lands after
            # disconnect() is a no-op rather than an AttributeError.
            self.gripper.reupload = lambda: (
                self.ctrl.reuploadScript() if self.ctrl is not None else None)
        self._abort.clear()

    def disconnect(self) -> None:
        """Shutdown path — the only place `ctrl` may be touched from another thread.

        Order matters: latch the abort flag first so a worker thread that is mid-move
        stops polling and issues its own stopJ/stopL, then close control → receive → io.
        """
        self._abort.set()
        self.gripper.disconnect()
        self._close_interfaces()

    def _close_interfaces(self) -> None:
        for iface in (self.ctrl, self.recv, self.io):
            if iface is None:
                continue
            try:
                close = getattr(iface, "disconnect", None)
                if close:
                    close()
            except Exception:
                pass
        self.ctrl = self.recv = self.io = None

    # ----------------------------------------------------------------- guards
    @property
    def stop_latched(self) -> bool:
        """True while a stop() is latched; only home() (or a reconnect) clears it."""
        return self._abort.is_set()

    def _check_abort(self) -> None:
        if self._abort.is_set():
            raise Aborted("robot stopped by stop(); send home to resume")

    def _require(self) -> None:
        if self.ctrl is None or self.recv is None:
            raise RobotFault("UR backend not connected")
        self._check_safety("emergency stop active", "protective stop active — reset in PolyScope")

    def _check_safety(self, es_msg: str, ps_msg: str | None = None) -> None:
        """N3: the hardware E-stop and a protective stop need different recoveries, so they
        are different exception types (EmergencyStop is a ProtectiveStop, so callers that
        only care about "the controller stopped us" still work)."""
        if self.recv.isEmergencyStopped():
            raise EmergencyStop(es_msg)
        if self.recv.isProtectiveStopped():
            raise ProtectiveStop(ps_msg if ps_msg is not None else es_msg)

    def _sp(self):
        return self.speeds[self._pace]

    # ------------------------------------------------------------ async moves
    def _async_state(self) -> tuple[bool, int]:
        """(running, raw value) of the current async operation. Worker thread only.

        ur_rtde `getAsyncOperationProgress()`: "<0 Indicates that no async operation is
        running or that an async operation has finished. The returned values of two
        consecutive async operations is never equal. Normally the returned values are
        toggled between -1 and -2. … >= 0 Indicates the progress of an async operation."
        `getAsyncOperationProgressEx()` is the non-deprecated form and exposes the same
        thing as `isAsyncOperationRunning()` / `value()`.
        """
        ex = getattr(self.ctrl, "getAsyncOperationProgressEx", None)
        if ex is not None:
            st = ex()
            return bool(st.isAsyncOperationRunning()), int(st.value())
        p = int(self.ctrl.getAsyncOperationProgress())
        return p >= 0, p

    def _at_rest(self) -> bool:
        getter = getattr(self.recv, "getActualQd", None)
        if getter is None:
            return True
        try:
            return all(abs(float(v)) < AT_REST_QD for v in getter())
        except Exception:
            return False

    def _stop_motion(self, kind: str) -> None:
        """Decelerate the arm from the worker thread, then report the abort.

        The `getattr` is inside the try on purpose: `disconnect()` may have set `self.ctrl`
        to None between the abort latching and this call, and that race is still an abort,
        not an `AttributeError` escaping as an unclassified failure.
        """
        try:
            stop = getattr(self.ctrl, "stopL" if kind == "L" else "stopJ")
            stop(STOP_DECEL)
        except Exception as e:            # comms died mid-stop: still an abort, not a failure
            raise Aborted(f"stop requested; stop{kind} failed: {e}") from e
        deadline = self._clock() + self.stop_timeout_s
        while self._clock() < deadline:
            try:
                running, _ = self._async_state()
            except Exception:
                break
            if not running:
                break
            time.sleep(self.poll_s)       # _abort is already set, so don't wait on it
        raise Aborted(f"motion stopped by stop() during move{kind}")

    def _wait_async(self, kind: str, baseline: int, reached) -> None:
        """Poll until the async operation finishes, the stop latch fires, or we time out."""
        started = False
        deadline = self._clock() + self.move_timeout_s
        while True:
            if self._abort.is_set():
                self._stop_motion(kind)   # always raises Aborted
            running, value = self._async_state()
            if running:
                started = True
            elif started or value != baseline:
                return                    # a *new* async operation has finished
            elif reached() and self._at_rest():
                return                    # controller never reported progress, but we are there
            if self._clock() > deadline:
                raise RobotFault("move timeout")
            if self._abort.wait(self.poll_s):
                self._stop_motion(kind)   # always raises Aborted

    def _move(self, kind: str, issue, reached) -> None:
        self._check_abort()
        baseline = self._async_state()[1]
        if not issue():
            self._check_safety("protective/emergency stop during motion")
            raise RobotFault(f"move{kind} refused")
        self._wait_async(kind, baseline, reached)
        self._check_safety("protective/emergency stop during motion")
        deadline = self._clock() + self.reach_grace_s
        while not reached():
            if self._clock() >= deadline:
                raise RobotFault("target not reached")
            time.sleep(min(self.poll_s, 0.05))

    def _moveJ(self, q):
        sp = self._sp()
        target = [float(x) for x in q]
        self._move("J", lambda: self.ctrl.moveJ(target, sp["joint_v"], sp["joint_a"], True),
                   lambda: self._q_reached(target))

    def _moveL(self, pose):
        sp = self._sp()
        target = [float(x) for x in pose]
        self._move("L", lambda: self.ctrl.moveL(target, sp["lin_v"], sp["lin_a"], True),
                   lambda: self._tcp_reached(target))

    def _q_reached(self, q) -> bool:
        try:
            actual = [float(x) for x in self.recv.getActualQ()]
        except Exception:
            return False
        return len(actual) >= 6 and max(abs(a - b) for a, b in zip(actual, q)) < Q_TOL_RAD

    def _tcp_reached(self, pose) -> bool:
        try:
            actual = [float(x) for x in self.recv.getActualTCPPose()]
        except Exception:
            return False
        return len(actual) >= 3 and max(abs(a - b) for a, b in zip(actual[:3], pose[:3])) < P_TOL_M

    # -------------------------------------------------------------------- IK
    def _ik(self, pose, node, slot: str):
        """Inverse kinematics for an approach pose, validated against the taught branch.

        Two failures are distinguished because they need different handling: the controller
        not answering at all (`_IKCallFailed` — the call raised, or it returned an empty /
        malformed list, which is what a control script that has just died does), versus a
        well-formed answer that sits off the taught branch.
        """
        try:
            sol = self.ctrl.getInverseKinematics(list(pose), qnear=list(node["q"]))
        except Exception as e:
            raise _IKCallFailed(f"IK call failed for {slot}: {e}") from e
        try:
            q = [float(x) for x in sol]
        except (TypeError, ValueError):
            q = []
        if len(q) != 6 or not all(math.isfinite(x) for x in q):
            raise _IKCallFailed(f"the controller returned no IK solution for {slot}")
        ref = [float(x) for x in node["q"]]
        worst = max(abs(a - b) for a, b in zip(q, ref))
        if worst > IK_BRANCH_TOL_RAD:
            raise RobotError(
                f"IK solution rejected for {slot}: off the taught branch by "
                f"{math.degrees(worst):.0f}deg (limit {math.degrees(IK_BRANCH_TOL_RAD):.0f}deg)")
        return q

    def _goto_above(self, slot: str, node: dict, above) -> None:
        """Reach the approach point above a slot: joint move when the controller's IK is
        usable, Cartesian move otherwise.

        The controller's ``getInverseKinematics`` is not dependable on every taught pose in
        this cell — on one slot it kills the RTDE control script outright. ``moveL`` asks the
        controller to solve the same target internally, seeded from the current configuration,
        so it cannot branch-flip; it is slower, which is why it is the fallback and not the
        default. If the point is genuinely out of reach, moveL fails on its own and the slot
        is reported exactly as before.
        """
        try:
            q = self._ik(above, node, slot)
        except RobotError as e:
            log.warning("%s: IK unusable (%s) — approaching with a Cartesian move", slot, e)
            if isinstance(e, _IKCallFailed):
                # The call may have taken the control script with it; without this the
                # fallback move fails too, for a reason that has nothing to do with reach.
                self._revive_control(slot)
            self._moveL(above)
        else:
            self._moveJ(q)

    def _revive_control(self, slot: str) -> None:
        """Bring the RTDE control script back after a call killed it.

        `reuploadScript()` is the cheap way and the one the URCap gripper already uses, but
        it is not always enough: measured on this controller, after the IK crash it returns
        True while `isProgramRunning()` stays False and every later control call answers
        with nothing. Reopening the interfaces does restore it, so that is the fallback.
        The stop latch is deliberately left alone — this is not a resume path.
        """
        try:
            if self.ctrl.reuploadScript() and self.ctrl.isProgramRunning():
                return
        except Exception:
            pass
        log.warning("%s: the control script did not come back — reopening the RTDE interfaces",
                    slot)
        self._close_interfaces()
        try:
            self.ctrl, self.recv, self.io = self._factory(self.ip)
        except Exception as e:
            raise RobotFault(f"lost the RTDE control script and could not reopen it: {e}") from e

    # ---------------------------------------------------------------- motions
    def _approach_and(self, slot: str, node: dict, close: bool) -> None:
        """transit → above target → straight down → gripper → straight up."""
        dz = float(self.cal["approach_dz_m"])
        pose = list(node["pose"])
        above = pose[:2] + [pose[2] + dz] + pose[3:]
        self._moveJ(self.cal["transit"]["q"])
        self._goto_above(slot, node, above)
        self._moveL(pose)
        if close:
            self.gripper.close()
        else:
            self.gripper.open()
        wait = self.settle if close else self.open_settle
        if wait and self._abort.wait(wait):
            raise Aborted("motion stopped by stop() during gripper settle")
        self._moveL(above)

    def _run(self, skill, fn):
        self._check_abort()
        self._require()
        self._busy = True
        try:
            fn()
        finally:
            self._busy = False
            self._last = skill

    # ----------------------------------------------------------------- skills
    def home(self) -> None:
        self._abort.clear()          # home is the resume path after a stop()
        self._run("home", lambda: self._moveJ(self.cal["home"]["q"]))

    def pick(self, depot_slot: str) -> None:
        validate_depot_slot(depot_slot)
        node = self.cal.get("depot", {}).get(depot_slot)
        if node is None:
            raise ValueError(f"depot slot {depot_slot} not in calibration")
        self._run("pick", lambda: self._approach_and(depot_slot, node, close=True))

    def place(self, staging_slot: str) -> None:
        validate_staging_slot(staging_slot)
        node = self.cal["staging"][staging_slot]
        self._run("place", lambda: self._approach_and(staging_slot, node, close=False))

    def open_gripper(self) -> None:
        def _open():
            self.gripper.open()
            if self.open_settle and self._abort.wait(self.open_settle):
                raise Aborted("motion stopped by stop() during gripper settle")
        self._run("open_gripper", _open)

    def close_gripper(self) -> None:
        # Gripper-only skills are also a resume path, like home(): they command no arm
        # motion, so the operator must not be forced to Home (and move the arm) just to
        # release or reset the gripper right after a STOP — that is exactly when they need
        # it (robot_bridge._LATCH_SAFE admits close_gripper/reset_gripper through the
        # bridge's latch for the same reason). Clearing here also matters mechanically: the
        # interruptible waits below poll this same `_abort` event, so leaving it set would
        # make them fire immediately.
        self._abort.clear()
        def _close():
            self.gripper.close()
            if self.settle and self._abort.wait(self.settle):
                raise Aborted("motion stopped by stop() during gripper settle")
        self._run("close_gripper", _close)

    def _io_set(self, do: int, level: bool) -> None:
        if not self.io.setToolDigitalOut(do, level):
            raise RobotError("gripper command refused")

    def _wait_or_abort(self, seconds: float, phase: str, on_abort=None) -> None:
        if seconds and self._abort.wait(seconds):
            if on_abort is not None:
                on_abort()
            raise Aborted(f"motion stopped by stop() during gripper reset ({phase})")

    def reset_gripper(self) -> None:
        """Verified recovery (2026-09-11) from a gripper fault latched by closing fully on
        air: power-cycle the tool voltage, then wake the gripper with a short DO0 pulse.

        Tool DO1 is never written here — the lab wiring rule is that it is asserted low
        exactly once, at `ToolDOGripper.connect()`, and never touched again. Sending the
        reset program over the controller kills the ur_rtde control script (same as
        `OnRobotURCapGripper`), so it is restored with `reuploadScript()` at the end. Every
        wait is interruptible by `stop()`, same as every other skill.

        Like `close_gripper`, this is also a resume path (see its comment): it commands no
        arm motion, so a STOP latch must not stand between the operator and recovering a
        faulted gripper.
        """
        self._abort.clear()
        def _reset():
            self._io_set(GRIPPER_TOOL_DO, False)     # DO0 = 0: the safe/open level, first
            if not self.ctrl.sendCustomScriptFunction(GRIPPER_RESET_SCRIPT_NAME,
                                                       GRIPPER_RESET_SCRIPT):
                raise RobotError("gripper reset script refused")
            self._wait_or_abort(self.gripper_reset_voltage_cycle_s, "tool-voltage cycle")
            self._wait_or_abort(self.gripper_reset_wake_wait_s, "wake wait")
            self._io_set(GRIPPER_TOOL_DO, True)      # wake pulse: DO0 high …
            self._wait_or_abort(self.gripper_reset_pulse_s, "wake pulse",
                                on_abort=lambda: self._io_set(GRIPPER_TOOL_DO, False))
            self._io_set(GRIPPER_TOOL_DO, False)     # … then low again
            self._wait_or_abort(self.gripper_reset_reupload_settle_s, "settle")
            self.ctrl.reuploadScript()
            if hasattr(self.gripper, "_closed"):
                self.gripper._closed = False          # the gripper wakes open (DO0 = 0)
        self._run("reset_gripper", _reset)

    def set_pace(self, level: str) -> None:
        self._pace = validate_pace(level)   # no motion — allowed while a stop is latched

    def stop(self) -> None:
        """Latch the stop. Safe from any thread: it never touches the control interface.

        The worker sees the flag within one poll period (~50 ms) and issues stopJ/stopL
        itself, then raises `Aborted`. `_busy` is *not* cleared here — the worker is still
        inside the move until it unwinds.
        """
        self._abort.set()

    def state(self) -> RobotState:
        """Cheap, thread-safe snapshot: receive interface and local flags only, never `ctrl`."""
        recv = self.recv
        connected = self.ctrl is not None and recv is not None
        safety = "disconnected"
        if connected:
            try:
                if recv.isEmergencyStopped():
                    safety = "estop"
                elif recv.isProtectiveStopped():
                    safety = "protective_stop"
                else:
                    safety = "normal"
            except Exception:
                connected, safety = False, "disconnected"
        return RobotState(connected=connected, backend=self.name, busy=self._busy,
                          gripper_closed=bool(self.gripper.is_closed()), pace=self._pace,
                          last_skill=self._last, safety=safety)
