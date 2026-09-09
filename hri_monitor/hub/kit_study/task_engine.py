"""Order state machine for the kit-assembly block. Publishes task.* on the bus.

Threading: mutate only via public methods; a non-reentrant lock guards them (tick runs
on the session ticker thread while HTTP handlers call mark_part_placed/next_order).
WARNING: topics are published while the lock is held — a bus subscriber must NEVER call
engine methods synchronously from its callback, or it will deadlock.
"""
from __future__ import annotations

import random
import threading
import time

from .orders import BlockSpec


class TaskEngine:
    def __init__(self, bus, block: BlockSpec, now=time.time, rng: random.Random | None = None):
        self.bus = bus
        self.block = block
        self.now = now
        self.rng = rng or random.Random()
        self._lock = threading.Lock()
        self._phase = "idle"
        self._order_i = -1
        self._step_i = 0
        self._parts = []                # remaining plan (list[PartSpec]) for current order
        self._placed = 0
        self._order_start = None
        self._perturb_at = None         # absolute time or None
        self._perturbation_applied = False

    # ---------------------------------------------------------------- public
    def start_block(self):
        with self._lock:
            if self._phase != "idle":
                return
            self._phase = "running"
            self.bus.publish("task.block_started", {"family": self.block.family,
                                                    "n_orders": len(self.block.orders)})
            self._begin_order(0)

    def next_order(self):
        with self._lock:
            if self._phase != "between_orders":
                return
            self._begin_order(self._order_i + 1)

    def mark_part_placed(self):
        with self._lock:
            if self._phase != "running":
                return
            part = self._parts[self._step_i]
            self.bus.publish("task.part_placed", {"order_id": self._order().id,
                                                  "step_index": self._step_i,
                                                  "part_id": part.id})
            self._step_i += 1
            if self._step_i >= len(self._parts):
                self._complete_order(timed_out=False)
            else:
                self._emit_step()
            self._emit_state()

    def tick(self):
        with self._lock:
            if self._phase != "running":
                self._emit_state()
                return
            order = self._order()
            t = self.now()
            if self._perturb_at is not None and not self._perturbation_applied and t >= self._perturb_at:
                self._apply_perturbation()
            if order.time_limit_s is not None:
                remaining = max(0.0, order.time_limit_s - (t - self._order_start))
                self.bus.publish("task.countdown", {"order_id": order.id,
                                                    "remaining_s": round(remaining, 1)})
                if remaining <= 0.0:
                    self._complete_order(timed_out=True)
            self._emit_state()

    def stop(self):
        with self._lock:
            self._phase = "done"
            self._emit_state()

    def state(self) -> dict:
        with self._lock:
            return self._state_unlocked()

    # --------------------------------------------------------------- private
    def _order(self):
        return self.block.orders[self._order_i]

    def _begin_order(self, index: int):
        self._order_i = index
        order = self._order()
        self._parts = list(order.parts)
        self._step_i = 0
        self._order_start = self.now()
        self._perturbation_applied = False
        self._perturb_at = None
        if order.perturbation is not None and order.time_limit_s:
            lo, hi = order.perturbation.window
            frac = self.rng.uniform(lo, hi)
            self._perturb_at = self._order_start + frac * order.time_limit_s
        self._phase = "running"
        self.bus.publish("task.order_started", {"order_id": order.id, "kind": order.kind,
                                                "order_index": index,
                                                "n_parts": len(self._parts),
                                                "time_limit_s": order.time_limit_s})
        self._emit_step()
        self._emit_state()

    def _emit_step(self):
        part = self._parts[self._step_i]
        self.bus.publish("task.step", {"order_id": self._order().id,
                                       "step_index": self._step_i, "part_id": part.id})

    def _apply_perturbation(self):
        remaining = list(range(self._step_i, len(self._parts)))
        if len(remaining) < 2:
            # Too few parts left to swap. Don't publish a no-op perturbation or mark
            # it applied: the trigger may retry on a later tick while the window/order
            # still allows it; if the order ends first the trial is simply unperturbed
            # (identifiable post hoc by the absent task.perturbation marker).
            return
        a, b = self.rng.sample(remaining, 2)
        self._parts[a], self._parts[b] = self._parts[b], self._parts[a]
        self._perturbation_applied = True
        self.bus.publish("task.perturbation", {"order_id": self._order().id,
                                               "kind": "swap_parts",
                                               "swap": [a, b],
                                               "order_started_ts": self._order_start})
        self._emit_step()

    def _complete_order(self, timed_out: bool):
        order = self._order()
        self.bus.publish("task.order_completed", {"order_id": order.id,
                                                  "duration_s": round(self.now() - self._order_start, 1),
                                                  "placed": self._step_i,
                                                  "n_parts": len(self._parts),
                                                  "timed_out": timed_out})
        if self._order_i + 1 >= len(self.block.orders):
            self._phase = "done"
            self.bus.publish("task.block_completed", {"family": self.block.family})
        else:
            self._phase = "between_orders"

    def _emit_state(self):
        # re-entrant safe: build the snapshot without re-acquiring the lock
        self.bus.publish("task.state", self._state_unlocked())

    def _state_unlocked(self) -> dict:
        # NOTE: identical to state() but assumes the lock is held
        order = self._order() if 0 <= self._order_i < len(self.block.orders) else None
        current = None
        remaining = None
        if self._phase == "running" and order is not None:
            p = self._parts[self._step_i]
            current = p.as_dict()
            if order.time_limit_s is not None:
                remaining = max(0.0, order.time_limit_s - (self.now() - self._order_start))
        return {
            "phase": self._phase,
            "order_index": self._order_i,
            "order_id": order.id if order else None,
            "order_name": order.name if order else None,
            "kind": order.kind if order else None,
            # Full assembly sequence (after any perturbation swap) with placement geometry, so
            # the participant screen can draw the figure, the built layers and the next brick.
            "parts": [p.as_dict() for p in self._parts] if order else [],
            "width_studs": order.width_studs if order else 0,
            "step_index": self._step_i,
            "n_parts": len(self._parts),
            "current_part": current,
            "remaining_s": round(remaining, 1) if remaining is not None else None,
            "queue": [o.kind for o in self.block.orders[self._order_i + 1:]] if order else
                     [o.kind for o in self.block.orders],
            "perturbation_applied": self._perturbation_applied,
        }
