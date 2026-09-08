"""Turns task progress + a supply profile into robot supply jobs.

Profile = the personalised collaboration behaviour (spec §3.6): look-ahead (how many parts
to keep staged ahead of the participant), preferred staging side, pace. v0 is rule-based;
C1 (Plan 3) will *set* the profile — this class stays the actuator.
Thread-safety: all bus callbacks only mutate state under `_lock` and enqueue bridge jobs.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass

from .orders import BlockSpec
from .robotd.base import STAGING_SLOTS, validate_pace

_SIDE_ORDER = {"L": ("L", "C", "R"), "C": ("C", "L", "R"), "R": ("R", "C", "L")}


@dataclass
class SupplyProfile:
    lookahead: int = 1
    side: str = "C"
    pace: str = "normal"
    announce: bool = False

    def __post_init__(self):
        if not 0 <= int(self.lookahead) <= 3:
            raise ValueError("lookahead must be 0..3")
        if self.side not in STAGING_SLOTS:
            raise ValueError(f"side must be one of {STAGING_SLOTS}")
        validate_pace(self.pace)


class SupplyController:
    _TOPICS = ("task.order_started", "task.part_placed", "task.order_completed", "task.block_completed",
               "robot.part_staged", "robot.skill_failed", "wizard.request_part")

    def __init__(self, bus, bridge, block: BlockSpec, profile: SupplyProfile | None = None):
        self.bus = bus
        self.bridge = bridge
        self.block = block
        self.profile = profile or SupplyProfile()
        self._lock = threading.Lock()
        self._order = None            # OrderSpec
        self._plan: list = []         # parts in supply order (step order)
        self._supplied: set[str] = set()
        self._inflight: dict[str, str] = {}   # part_id -> slot
        self._staged: dict[str, str] = {}     # slot -> part_id
        self._retried: set[str] = set()
        self._requests = 0
        self._active = False

    # -------------------------------------------------------------- lifecycle
    def start(self) -> None:
        self._active = True
        for t in self._TOPICS:
            self.bus.subscribe(t, self._on_bus)
        self.bridge.submit("set_pace", level=self.profile.pace)
        self._emit()

    def stop(self) -> None:
        self._active = False
        for t in self._TOPICS:
            self.bus.unsubscribe(t, self._on_bus)

    def set_profile(self, **changes) -> None:
        with self._lock:
            self.profile = SupplyProfile(**{**asdict(self.profile), **changes})
            self.bridge.submit("set_pace", level=self.profile.pace)
        self._emit()
        self._replenish()

    def status(self) -> dict:
        with self._lock:
            nxt = next((p.id for p in self._plan if p.id not in self._supplied and p.id not in self._inflight), None)
            return {"profile": asdict(self.profile),
                    "order_id": self._order.id if self._order else None,
                    "staged": dict(self._staged),
                    "inflight": list(self._inflight),
                    "supplied": sorted(self._supplied),
                    "next_part_id": nxt}

    # ---------------------------------------------------------------- events
    def _on_bus(self, message) -> None:
        if not self._active:
            return
        topic, data = message["topic"], message["data"]
        if topic == "task.order_started":
            with self._lock:
                self._order = self.block.orders[int(data["order_index"])]
                self._plan = list(self._order.parts)
                self._supplied.clear(); self._inflight.clear(); self._staged.clear()
                self._retried.clear(); self._requests = 0
            self._emit(); self._replenish()
        elif topic == "task.part_placed":
            with self._lock:
                slot = next((s for s, pid in self._staged.items() if pid == data["part_id"]), None)
                if slot is not None:
                    del self._staged[slot]
            self._emit(); self._replenish()
        elif topic in ("task.order_completed", "task.block_completed"):
            with self._lock:
                self._plan = []; self._inflight.clear()
            self._emit()
        elif topic == "robot.part_staged":
            with self._lock:
                pid = data["part_id"]
                if pid in self._inflight:
                    del self._inflight[pid]
                self._staged[data["slot"]] = pid
                self._supplied.add(pid)
            self._emit(); self._replenish()
        elif topic == "robot.skill_failed":
            retry = False
            pid = (data.get("args") or {}).get("part_id")
            with self._lock:
                if pid and pid in self._inflight:
                    del self._inflight[pid]
                    retry = pid not in self._retried and not data.get("protective_stop")
                    if retry:
                        self._retried.add(pid)
            self._emit()
            if pid and retry:
                self._replenish()
        elif topic == "wizard.request_part":
            with self._lock:
                self._requests += 1
            self._replenish(on_request=True)

    # --------------------------------------------------------------- policy
    def _free_slot(self) -> str | None:
        for s in _SIDE_ORDER[self.profile.side]:
            if s not in self._staged and s not in self._inflight.values():
                return s
        return None

    def _replenish(self, on_request: bool = False) -> None:
        decisions = []
        with self._lock:
            if self._order is None:
                return
            ahead = len(self._staged) + len(self._inflight)
            budget = self.profile.lookahead
            if budget == 0:
                budget = 1 if (on_request or self._requests > len(self._supplied) + len(self._inflight)) else 0
            while ahead < budget:
                part = next((p for p in self._plan
                             if p.id not in self._supplied and p.id not in self._inflight), None)
                slot = self._free_slot()
                if part is None or slot is None:
                    break
                self._inflight[part.id] = slot
                decisions.append((part, slot, "request" if on_request else f"lookahead={self.profile.lookahead}"))
                ahead += 1
        for part, slot, reason in decisions:
            self.bus.publish("supply.decision", {"part_id": part.id, "slot": slot, "reason": reason})
            self.bridge.supply(part.id, part.depot_slot, slot)
        if decisions:
            self._emit()

    def _emit(self) -> None:
        self.bus.publish("supply.state", self.status())
