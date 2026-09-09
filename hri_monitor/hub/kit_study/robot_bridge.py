"""Executes robot skills on a dedicated worker thread and narrates them on the bus.

Bus callbacks elsewhere (TaskEngine, SupplyController) call `submit()`/`supply()` — which
only enqueue — so nobody ever blocks on robot motion inside a bus callback.

Safety latch: a wizard STOP, a backend protective stop, or a safety transition seen by the
idle monitor *latches* the bridge. While latched only `home` is accepted; every other skill
is refused with `robot.rejected` so that nothing (SupplyController included) can put the
robot back in motion behind the operator's back. A successful `home` clears the latch and
publishes `robot.resumed`.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
import uuid

from .robotd.base import Aborted, ProtectiveStop, RobotBackend, RobotError

log = logging.getLogger(__name__)

# Backend safety values that latch the bridge, mapped to the latch reason.
_SAFETY_LATCH = {"protective_stop": "protective_stop", "estop": "emergency_stop"}
_DISCONNECTED = {"connected": False, "backend": "?", "busy": False, "gripper_closed": False,
                 "pace": "normal", "last_skill": None, "safety": "disconnected"}


class RobotBridge:
    def __init__(self, bus, backend: RobotBackend, now=time.time, monitor_interval: float = 0.33):
        self.bus = bus
        self.backend = backend
        self.now = now
        self.monitor_interval = float(monitor_interval)
        self._q: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._monitor: threading.Thread | None = None
        self._stop_evt = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._lock = threading.Lock()
        self._active = False  # True when a job has been dequeued and not yet finished
        self._latched: str | None = None   # None | "estop" | "protective_stop" | "emergency_stop"
        self._last_safety: str | None = None
        self._last_state: dict | None = None

    # -------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_evt.clear()
        self._connect_quietly()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="robot-bridge")
        self._thread.start()
        self._monitor = threading.Thread(target=self._monitor_loop, daemon=True, name="robot-monitor")
        self._monitor.start()
        self._publish_state()

    def stop(self) -> None:
        self._stop_evt.set()
        if self._thread is not None:
            self._q.put(None)       # only when someone is there to consume the sentinel
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                log.warning("RobotBridge worker thread did not exit within timeout")
            else:
                self._thread = None
        if self._monitor is not None:
            self._monitor.join(timeout=2.0)
            if self._monitor.is_alive():
                log.warning("RobotBridge monitor thread did not exit within timeout")
            else:
                self._monitor = None
        try:
            if self.backend.state().connected:
                self.backend.disconnect()
        except Exception as e:
            log.warning("robot backend disconnect failed: %s", e)

    def connect(self) -> dict:
        """Re-attempt the backend connection (I1 recovery); never raises."""
        self._connect_quietly()
        self._publish_state()
        return self.state()

    def _connect_quietly(self) -> None:
        """An unreachable robot must not stop the app from starting (I1)."""
        try:
            if not self.backend.state().connected:
                self.backend.connect()
        except Exception as e:
            log.warning("robot backend connect failed (%s: %s); running disconnected",
                        type(e).__name__, e)

    # ---------------------------------------------------------------- submit
    def submit(self, skill: str, **args) -> str | None:
        """Enqueue a skill. Returns None (and publishes `robot.rejected`) while latched."""
        job_id = uuid.uuid4().hex[:8]
        with self._lock:
            latched = self._latched
            if latched is None or skill == "home":
                self._idle.clear()
                self._q.put((job_id, skill, args))
                latched = None
        if latched is not None:
            self.bus.publish("robot.rejected", {"skill": skill, "args": args, "reason": latched})
            return None
        self.bus.publish("robot.skill_queued", {"job_id": job_id, "skill": skill, "args": args})
        return job_id

    def supply(self, part_id: str, depot_slot: str, staging_slot: str) -> str | None:
        return self.submit("supply", part_id=part_id, depot_slot=depot_slot, staging_slot=staging_slot)

    def clear_queue(self) -> int:
        n = 0
        with self._lock:
            while True:
                try:
                    self._q.get_nowait(); n += 1
                except queue.Empty:
                    break
            if self._q.empty() and not self._active:
                self._idle.set()
        return n

    def estop(self) -> None:
        self.clear_queue()
        with self._lock:
            self._latched = "estop"
        try:
            self.backend.stop()
        finally:
            self.bus.publish("robot.estop", {"reason": "estop", "source": "wizard"})
            self._publish_state()

    def queue_size(self) -> int:
        return self._q.qsize()

    def busy(self) -> bool:
        """True while a job is queued or in flight (session teardown / start guards)."""
        return not self._idle.is_set()

    def wait_idle(self, timeout: float) -> bool:
        return self._idle.wait(timeout)

    def latched(self) -> str | None:
        with self._lock:
            return self._latched

    def state(self) -> dict:
        with self._lock:
            latched = self._latched
        return {**self._backend_state(), "queue": self._q.qsize(), "latched": latched}

    # ---------------------------------------------------------------- worker
    def _loop(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                break
            with self._lock:
                self._active = True
            job_id, skill, args = item
            self.bus.publish("robot.skill_started", {"job_id": job_id, "skill": skill, "args": args})
            t0 = self.now()
            resumed = False
            try:
                self._execute(skill, args, job_id)
                if skill == "home":
                    resumed = self._clear_latch()
                self.bus.publish("robot.skill_done", {"job_id": job_id, "skill": skill, "args": args,
                                                      "duration_s": round(self.now() - t0, 3)})
                if resumed:
                    self.bus.publish("robot.resumed", {})
            except RobotError as e:
                protective = isinstance(e, ProtectiveStop)
                self.bus.publish("robot.skill_failed", {"job_id": job_id, "skill": skill, "args": args,
                                                        "error": str(e),
                                                        "protective_stop": protective,
                                                        "aborted": isinstance(e, Aborted)})
                if protective:
                    self._latch("protective_stop", "backend")
            except Exception as e:  # never let the worker die
                self.bus.publish("robot.skill_failed", {"job_id": job_id, "skill": skill, "args": args,
                                                        "error": f"{type(e).__name__}: {e}",
                                                        "protective_stop": False, "aborted": False})
            finally:
                self._publish_state()
                with self._lock:
                    self._active = False
                    if self._q.empty():
                        self._idle.set()

    def _execute(self, skill: str, args: dict, job_id: str) -> None:
        b = self.backend
        if skill == "supply":
            b.pick(args["depot_slot"])
            b.place(args["staging_slot"])
            self.bus.publish("robot.part_staged", {"part_id": args["part_id"], "depot_slot": args["depot_slot"],
                                                   "slot": args["staging_slot"], "job_id": job_id})
        elif skill == "home":
            b.home()
        elif skill == "pick":
            b.pick(args["depot_slot"])
        elif skill == "place":
            b.place(args["staging_slot"])
        elif skill == "open_gripper":
            b.open_gripper()
        elif skill == "set_pace":
            b.set_pace(args["level"])
        else:
            raise RobotError(f"unknown skill {skill!r}")

    # ----------------------------------------------------------------- latch
    def _latch(self, reason: str, source: str) -> bool:
        """Latch on a transition; publishes `robot.estop` outside the lock. Idempotent."""
        with self._lock:
            if self._latched == reason:
                return False
            self._latched = reason
        # jobs queued before the latch must not run either (they would fail identically)
        self.clear_queue()
        self.bus.publish("robot.estop", {"reason": reason, "source": source})
        self._publish_state()
        return True

    def _clear_latch(self) -> bool:
        with self._lock:
            if self._latched is None:
                return False
            self._latched = None
        return True

    # --------------------------------------------------------------- monitor
    def _monitor_loop(self) -> None:
        """Poll the backend while idle so a protective stop can never go unnoticed (C4)."""
        while not self._stop_evt.wait(self.monitor_interval):
            if self.busy():
                continue          # the worker owns the backend; its own publishes cover state
            try:
                st = self.state()
            except Exception:     # pragma: no cover - _backend_state already guards
                continue
            safety = st.get("safety")
            if safety != self._last_safety:
                self._last_safety = safety
                reason = _SAFETY_LATCH.get(safety)
                if reason is not None:
                    self._latch(reason, "monitor")
                    continue      # _latch already published the state
            if st != self._last_state:
                self._publish_state(st)

    # ----------------------------------------------------------------- state
    def _backend_state(self) -> dict:
        try:
            return self.backend.state().as_dict()
        except Exception as e:
            log.debug("robot backend state() failed: %s", e)
            return {**_DISCONNECTED, "backend": getattr(self.backend, "name", "?")}

    def _publish_state(self, st: dict | None = None) -> None:
        st = self.state() if st is None else st
        self._last_state = st
        self.bus.publish("robot.state", st)
