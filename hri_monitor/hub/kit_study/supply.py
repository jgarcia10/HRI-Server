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
               "task.step", "task.perturbation",
               "robot.part_staged", "robot.skill_failed", "wizard.request_part", "wizard.slot_cleared")

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
        self._failed: set[str] = set()        # terminal failures (F1)
        self._current_part_id: str | None = None  # from task.step (F2)
        self._blocked: dict | None = None    # blocked detection (F2)
        self._blocked_published: bool = False  # track published state to avoid spam
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
        profile_to_set = None
        with self._lock:
            profile_to_set = SupplyProfile(**{**asdict(self.profile), **changes})
            self.profile = profile_to_set
        # F3: exit lock before calling bridge.submit
        self.bridge.submit("set_pace", level=self.profile.pace)
        self._emit()
        self._replenish()

    def status(self) -> dict:
        with self._lock:
            nxt = next((p.id for p in self._plan
                       if p.id not in self._supplied and p.id not in self._inflight and p.id not in self._failed),
                       None)
            return {"profile": asdict(self.profile),
                    "order_id": self._order.id if self._order else None,
                    "staged": dict(self._staged),
                    "inflight": list(self._inflight),
                    "supplied": sorted(self._supplied),
                    "failed": sorted(self._failed),
                    "blocked": self._blocked,
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
                self._retried.clear(); self._failed.clear()
                self._current_part_id = None
                self._blocked = None; self._blocked_published = False
                self._requests = 0
            self._emit(); self._replenish()
        elif topic == "task.step":
            # F2: track current part for prioritized selection
            with self._lock:
                self._current_part_id = data.get("part_id")
            self._emit(); self._replenish()
        elif topic == "task.perturbation":
            # F2: swap plan to stay synced with engine
            with self._lock:
                swap = data.get("swap")
                if swap and len(swap) == 2:
                    a, b = swap
                    if 0 <= a < len(self._plan) and 0 <= b < len(self._plan):
                        self._plan[a], self._plan[b] = self._plan[b], self._plan[a]
            self._emit(); self._replenish()
        elif topic == "task.part_placed":
            with self._lock:
                slot = next((s for s, pid in self._staged.items() if pid == data["part_id"]), None)
                if slot is not None:
                    del self._staged[slot]
            self._emit(); self._replenish()
        elif topic in ("task.order_completed", "task.block_completed"):
            with self._lock:
                self._plan = []; self._inflight.clear(); self._blocked = None; self._blocked_published = False
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
            pid = (data.get("args") or {}).get("part_id")
            pid_was_inflight = False
            with self._lock:
                if pid and pid in self._inflight:
                    pid_was_inflight = True
                    del self._inflight[pid]
                    protective_stop = data.get("protective_stop")
                    if protective_stop:
                        # F1+F4: protective stop → terminal failure
                        self._failed.add(pid)
                    elif pid not in self._retried:
                        # F1+F4: first failure → mark retried and retry
                        self._retried.add(pid)
                    else:
                        # F1+F4: second failure → terminal
                        self._failed.add(pid)
                    # N4: only reset blocked if we handled this pid
                    self._blocked = None; self._blocked_published = False
            self._emit()
            # Always replenish to handle retry or blocked detection
            self._replenish()
        elif topic == "wizard.request_part":
            with self._lock:
                self._requests += 1
                # F5: if current part is failed, clear it for retry
                if self._current_part_id and self._current_part_id in self._failed:
                    self._failed.discard(self._current_part_id)
                    self._retried.discard(self._current_part_id)
            self._replenish(on_request=True)
        elif topic == "wizard.slot_cleared":
            # F2: experimenter physically removed part from slot
            slot = data.get("slot")
            with self._lock:
                if slot and slot in self._staged:
                    del self._staged[slot]
                self._blocked = None; self._blocked_published = False
            self._emit(); self._replenish()

    # --------------------------------------------------------------- policy
    def _free_slot(self) -> str | None:
        for s in _SIDE_ORDER[self.profile.side]:
            if s not in self._staged and s not in self._inflight.values():
                return s
        return None

    def _replenish(self, on_request: bool = False) -> None:
        decisions = []
        to_publish_blocked = None
        with self._lock:
            if self._order is None:
                return
            ahead = len(self._staged) + len(self._inflight)
            budget = self.profile.lookahead
            if budget == 0:
                budget = 1 if (on_request or self._requests > len(self._supplied) + len(self._inflight)) else 0

            # N3: Request-current rule (explicitly bypass lookahead for current part on wizard request).
            # The current part is due on its turn, not ahead of the queue; serve it even at budget
            # if not yet staged/inflight/failed. Requires a free slot. Publish as "request-current".
            if on_request and self._current_part_id:
                for p in self._plan:
                    if p.id == self._current_part_id:
                        if (p.id not in self._supplied and p.id not in self._inflight and p.id not in self._failed):
                            slot = self._free_slot()
                            if slot is not None:
                                self._inflight[p.id] = slot
                                decisions.append((p, slot, "request-current"))
                                ahead += 1
                        break

            while ahead < budget:
                # F1+F3: selection excludes failed parts
                # F2: prioritize current part if it's a candidate
                current_candidate = None
                if self._current_part_id:
                    for p in self._plan:
                        if p.id == self._current_part_id:
                            if (p.id not in self._supplied and p.id not in self._inflight and p.id not in self._failed):
                                current_candidate = p
                            break

                if current_candidate:
                    part = current_candidate
                else:
                    part = next((p for p in self._plan
                                 if p.id not in self._supplied and p.id not in self._inflight and p.id not in self._failed),
                                None)

                slot = self._free_slot()
                if part is None or slot is None:
                    break
                self._inflight[part.id] = slot
                decisions.append((part, slot, "request" if on_request else f"lookahead={self.profile.lookahead}"))
                ahead += 1

            # F6: blocked detection (N1: snapshot only, publish outside lock)
            new_blocked = None
            if self._current_part_id:
                in_staged = any(pid == self._current_part_id for pid in self._staged.values())
                in_inflight = self._current_part_id in self._inflight
                in_failed = self._current_part_id in self._failed
                free_slot = self._free_slot()

                if not in_staged and not in_inflight:
                    if free_slot is None and not in_failed:
                        # mat_full: current part not staged/inflight, no free slots, not failed yet
                        new_blocked = {"reason": "mat_full", "needed": self._current_part_id, "staged": dict(self._staged)}
                    elif in_failed:
                        # part_failed: current part is terminal failure
                        new_blocked = {"reason": "part_failed", "needed": self._current_part_id, "staged": dict(self._staged)}

            self._blocked = new_blocked

            # N1: Snapshot for publishing; decide transition under lock
            is_blocked = self._blocked is not None
            if is_blocked and not self._blocked_published:
                to_publish_blocked = dict(self._blocked)
                self._blocked_published = True
            elif not is_blocked and self._blocked_published:
                self._blocked_published = False

        # N1: Publish decisions and blocked outside the lock
        for part, slot, reason in decisions:
            self.bus.publish("supply.decision", {"part_id": part.id, "slot": slot, "reason": reason})
            self.bridge.supply(part.id, part.depot_slot, slot)
        if decisions:
            self._emit()

        # N1: Publish blocked event outside lock (once per transition, no spam)
        if to_publish_blocked is not None:
            self.bus.publish("supply.blocked", to_publish_blocked)

    def _emit(self) -> None:
        self.bus.publish("supply.state", self.status())
