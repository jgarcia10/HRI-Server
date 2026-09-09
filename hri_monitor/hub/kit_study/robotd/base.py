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
    """A skill failed (grasp miss, unreachable, comms)."""


class ProtectiveStop(RobotError):
    """The controller entered protective/emergency stop; motion is refused until reset."""


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
