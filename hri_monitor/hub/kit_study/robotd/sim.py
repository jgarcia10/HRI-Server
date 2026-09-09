"""Kinematic timing model of the robot: same skills, no hardware. Durations are configurable
so the sim can be set to the cycle times measured on the UR5 at M4."""
from __future__ import annotations

import random
import threading
import time

from .base import (PACE_FACTOR, Aborted, RobotBackend, RobotError, RobotState, validate_depot_slot,
                   validate_pace, validate_staging_slot)

DEFAULT_TIMING = {"home": 3.0, "pick": 2.5, "place": 2.5, "open_gripper": 0.5, "noise_std": 0.2}


class SimBackend(RobotBackend):
    name = "sim"

    def __init__(self, timing: dict | None = None, failure_rate: float = 0.0, rng=None,
                 sleep=time.sleep):
        self.timing = {**DEFAULT_TIMING, **(timing or {})}
        self.failure_rate = float(failure_rate)
        self.rng = rng or random.Random()
        self._sleep = sleep
        self._abort = threading.Event()   # set by stop(): interrupts the running skill
        self._connected = False
        self._busy = False
        self._gripper_closed = False
        self._pace = "normal"
        self._last = None

    # ------------------------------------------------------------- lifecycle
    def connect(self) -> None:
        self._abort.clear()
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    # ---------------------------------------------------------------- skills
    def _run(self, skill: str) -> None:
        if not self._connected:
            raise RobotError("sim backend not connected")
        if self._abort.is_set():
            raise Aborted(f"{skill} refused: stop() latched")
        base = float(self.timing[skill])
        noise = self.rng.gauss(0.0, float(self.timing["noise_std"])) if self.timing["noise_std"] else 0.0
        dur = max(0.05, base + noise) * PACE_FACTOR[self._pace]
        self._busy = True
        try:
            if self._sleep is time.sleep:
                # wait on the abort event instead of sleeping, so stop() interrupts the motion
                if self._abort.wait(dur):
                    raise Aborted(f"{skill} interrupted by stop()")
            else:
                self._sleep(dur)          # injected clock (fast tests): no real waiting to abort
                if self._abort.is_set():
                    raise Aborted(f"{skill} interrupted by stop()")
        finally:
            self._busy = False
            self._last = skill

    def home(self) -> None:
        self._abort.clear()               # homing is the reset gesture
        self._run("home")

    def pick(self, depot_slot: str) -> None:
        validate_depot_slot(depot_slot)
        self._run("pick")
        if self.rng.random() < self.failure_rate:
            self._gripper_closed = False
            raise RobotError(f"simulated grasp failure at {depot_slot}")
        self._gripper_closed = True

    def place(self, staging_slot: str) -> None:
        validate_staging_slot(staging_slot)
        self._run("place")
        self._gripper_closed = False

    def open_gripper(self) -> None:
        self._run("open_gripper")
        self._gripper_closed = False

    def set_pace(self, level: str) -> None:
        self._pace = validate_pace(level)

    def stop(self) -> None:
        """Latch the abort. `_busy` is owned by the running skill and cleared when it
        unwinds (same contract as `URBackend.stop`) — clearing it here would report the
        robot as idle while a motion is still finishing."""
        self._abort.set()

    def state(self) -> RobotState:
        return RobotState(connected=self._connected, backend=self.name, busy=self._busy,
                          gripper_closed=self._gripper_closed, pace=self._pace,
                          last_skill=self._last,
                          safety="normal" if self._connected else "disconnected")
