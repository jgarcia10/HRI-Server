"""UR5 backend over ur_rtde. Fixed taught waypoints; no planning; PolyScope safety is authoritative."""
from __future__ import annotations

import time
from pathlib import Path

import yaml

from .base import (PACE_LEVELS, RobotBackend, RobotError, ProtectiveStop, RobotState, STAGING_SLOTS,
                   validate_depot_slot, validate_pace, validate_staging_slot)

GRIPPER_TOOL_DO = 0          # tool digital output 0 == legacy SetIO(fun=1, pin=16); True = close
DEFAULT_SPEEDS = {
    "normal": {"joint_v": 0.6, "joint_a": 0.8, "lin_v": 0.15, "lin_a": 0.5},
    "slow":   {"joint_v": 0.3, "joint_a": 0.5, "lin_v": 0.08, "lin_a": 0.3},
}


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
                 gripper_settle_s: float = 1.0, rtde_factory=None, sleep=time.sleep):
        self.ip = ip
        self.cal = calibration
        self.speeds = speeds or DEFAULT_SPEEDS
        self.settle = float(gripper_settle_s)
        self._factory = rtde_factory or _default_factory
        self._sleep = sleep
        self.ctrl = self.recv = self.io = None
        self._pace = "normal"
        self._busy = False
        self._gripper_closed = False
        self._last = None

    # -------------------------------------------------------------- lifecycle
    def connect(self) -> None:
        try:
            self.ctrl, self.recv, self.io = self._factory(self.ip)
        except Exception as e:
            raise RobotError(f"cannot connect to UR at {self.ip}: {e}") from e

    def disconnect(self) -> None:
        if self.ctrl is not None:
            try:
                self.ctrl.disconnect()
            finally:
                self.ctrl = self.recv = self.io = None

    # ----------------------------------------------------------------- guards
    def _require(self) -> None:
        if self.ctrl is None or self.recv is None:
            raise RobotError("UR backend not connected")
        if self.recv.isEmergencyStopped():
            raise ProtectiveStop("emergency stop active")
        if self.recv.isProtectiveStopped():
            raise ProtectiveStop("protective stop active — reset in PolyScope")

    def _sp(self):
        return self.speeds[self._pace]

    def _moveJ(self, q):
        sp = self._sp()
        if not self.ctrl.moveJ(list(q), sp["joint_v"], sp["joint_a"]):
            raise RobotError("moveJ refused")

    def _moveL(self, pose):
        sp = self._sp()
        if not self.ctrl.moveL(list(pose), sp["lin_v"], sp["lin_a"]):
            raise RobotError("moveL refused")

    def _approach_and(self, node: dict, close: bool) -> None:
        """transit → above target → straight down → gripper → straight up."""
        dz = float(self.cal["approach_dz_m"])
        pose = list(node["pose"])
        above = pose[:2] + [pose[2] + dz] + pose[3:]
        self._moveJ(self.cal["transit"]["q"])
        q_above = self.ctrl.getInverseKinematics(above, qnear=list(node["q"]))
        self._moveJ(q_above)
        self._moveL(pose)
        self.io.setToolDigitalOut(GRIPPER_TOOL_DO, close)
        self._gripper_closed = close
        if self.settle:
            self._sleep(self.settle)
        self._moveL(above)

    def _run(self, skill, fn):
        self._require()
        self._busy = True
        try:
            fn()
        finally:
            self._busy = False
            self._last = skill

    # ---------------------------------------------------------------- skills
    def home(self) -> None:
        self._run("home", lambda: self._moveJ(self.cal["home"]["q"]))

    def pick(self, depot_slot: str) -> None:
        validate_depot_slot(depot_slot)
        node = self.cal.get("depot", {}).get(depot_slot)
        if node is None:
            raise ValueError(f"depot slot {depot_slot} not in calibration")
        self._run("pick", lambda: self._approach_and(node, close=True))

    def place(self, staging_slot: str) -> None:
        validate_staging_slot(staging_slot)
        node = self.cal["staging"][staging_slot]
        self._run("place", lambda: self._approach_and(node, close=False))

    def open_gripper(self) -> None:
        def _open():
            self.io.setToolDigitalOut(GRIPPER_TOOL_DO, False)
            self._gripper_closed = False
            if self.settle:
                self._sleep(self.settle)
        self._run("open_gripper", _open)

    def set_pace(self, level: str) -> None:
        self._pace = validate_pace(level)

    def stop(self) -> None:
        if self.ctrl is not None:
            try:
                self.ctrl.stopJ(2.0)
            except Exception:
                pass
        self._busy = False

    def state(self) -> RobotState:
        if self.recv is None:
            safety = "disconnected"
        elif self.recv.isEmergencyStopped():
            safety = "estop"
        elif self.recv.isProtectiveStopped():
            safety = "protective_stop"
        else:
            safety = "normal"
        return RobotState(connected=self.ctrl is not None, backend=self.name, busy=self._busy,
                          gripper_closed=self._gripper_closed, pace=self._pace, last_skill=self._last,
                          safety=safety)
