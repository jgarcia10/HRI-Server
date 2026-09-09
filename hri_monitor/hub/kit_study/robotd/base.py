"""Skill-level robot interface. Backends implement fixed, taught motions — never planning."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass

STAGING_SLOTS = ("L", "C", "R")
PACE_LEVELS = ("slow", "normal")
PACE_FACTOR = {"slow": 1.6, "normal": 1.0}
_DEPOT_SLOT = re.compile(r"^[A-Z]{2}\d{1,2}$")   # RD1, OR3, BL12 …


class RobotError(Exception):
    """A skill failed for a reason that is *specific to this attempt* — a grasp miss, a
    gripper command the tool refused, an IK solution off the taught branch. Retrying the
    same part (once) is a sensible response."""


class RobotFault(RobotError):
    """The robot refused or failed to *move at all*: not connected, moveJ/moveL refused,
    move timeout, target not reached.

    N2: these are not grasp failures — the next part would fail identically, so the whole
    remaining order would go terminal within milliseconds. The bridge latches on them and
    supply pauses exactly as it does for a protective stop."""


class ProtectiveStop(RobotError):
    """The controller entered a protective stop; motion is refused until reset in PolyScope."""


class EmergencyStop(ProtectiveStop):
    """The hardware E-stop is pressed. Recovery differs from a protective stop (release the
    button and re-power), so it is reported separately — see N3."""


class Aborted(RobotError):
    """The skill was interrupted by stop(); not a grasp failure — never retry automatically."""


@dataclass
class RobotState:
    connected: bool
    backend: str
    busy: bool
    gripper_closed: bool
    pace: str
    last_skill: str | None
    safety: str  # "normal" | "protective_stop" | "estop" | "disconnected"

    def as_dict(self) -> dict:
        return asdict(self)


def validate_depot_slot(slot: str) -> str:
    if not _DEPOT_SLOT.match(slot or ""):
        raise ValueError(f"invalid depot slot {slot!r} (expected e.g. RD1)")
    return slot


def validate_staging_slot(slot: str) -> str:
    if slot not in STAGING_SLOTS:
        raise ValueError(f"invalid staging slot {slot!r} (expected one of {STAGING_SLOTS})")
    return slot


def validate_pace(level: str) -> str:
    if level not in PACE_LEVELS:
        raise ValueError(f"invalid pace {level!r} (expected one of {PACE_LEVELS})")
    return level


class RobotBackend(ABC):
    name: str = "abstract"

    @abstractmethod
    def connect(self) -> None: ...
    @abstractmethod
    def disconnect(self) -> None: ...
    @abstractmethod
    def home(self) -> None: ...
    @abstractmethod
    def pick(self, depot_slot: str) -> None: ...
    @abstractmethod
    def place(self, staging_slot: str) -> None: ...
    @abstractmethod
    def open_gripper(self) -> None: ...
    @abstractmethod
    def set_pace(self, level: str) -> None: ...
    @abstractmethod
    def stop(self) -> None: ...
    @abstractmethod
    def state(self) -> RobotState: ...
