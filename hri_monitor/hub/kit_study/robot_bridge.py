"""Executes robot skills on a dedicated worker thread and narrates them on the bus.

Bus callbacks elsewhere (TaskEngine, SupplyController) call `submit()`/`supply()` — which
only enqueue — so nobody ever blocks on robot motion inside a bus callback.

Safety latch: a wizard STOP, a backend protective stop / E-stop, a robot fault (the arm
refused or failed to move) or a safety transition seen by the idle monitor *latches* the
bridge. While latched only the two skills that cannot move the arm are accepted — `home`
(the resume path) and `set_pace` (N1: a profile change must still reach the backend, or the
robot silently runs at the wrong speed after the latch clears). Every other skill is refused
with `robot.rejected` so that nothing (SupplyController included) can put the robot back in
motion behind the operator's back. A successful `home` clears the latch and publishes
`robot.resumed`.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
import uuid

from .robotd.base import (Aborted, EmergencyStop, ProtectiveStop, RobotBackend, RobotError,
                          RobotFault)

log = logging.getLogger(__name__)

# Skills that move nothing and are therefore safe to run while the bridge is latched.
_LATCH_SAFE = ("home", "set_pace")
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
        # None | "estop" | "protective_stop" | "emergency_stop" | "robot_fault"
        self._latched: str | None = None
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
        """Enqueue a skill. Returns None (and publishes `robot.rejected`) while latched.

        `home` and `set_pace` are admitted through the latch: neither commands a motion
        (`URBackend.set_pace`/`SimBackend.set_pace` only assign the speed profile).
        """
        job_id = uuid.uuid4().hex[:8]
        with self._lock:
            latched = self._latched
            if latched is None or skill in _LATCH_SAFE:
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
        # Latch *before* draining: a submit() racing the STOP must be rejected, not slip
        # into the queue behind the drain and run once the backend stop returns.
        with self._lock:
            self._latched = "estop"
        self.clear_queue()
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
                self._report_failure(job_id, skill, args, e, str(e))
            except Exception as e:  # never let the worker die
                # Raw RTDE errors (socket dropped mid-move) are not RobotErrors but must still
                # latch when the backend now reports itself disconnected.
                self._report_failure(job_id, skill, args, e, f"{type(e).__name__}: {e}")
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

    # ------------------------------------------------------- failure classing
    def _report_failure(self, job_id: str, skill: str, args: dict, exc: RobotError,
                        error: str) -> None:
        """Publish `robot.skill_failed` and latch when the *robot*, not the grasp, failed.

        N2/N3 — three kinds of failure need three different reactions:
        * `EmergencyStop`/`ProtectiveStop` → latch as `emergency_stop`/`protective_stop`.
        * `RobotFault` (not connected, move refused/timed out, target not reached) or *any*
          failure raised while the backend reports itself disconnected → latch as
          `robot_fault`. Without this the next part fails identically and the whole order
          goes terminal in milliseconds while the wizard is told nothing.
        * everything else (grasp miss, gripper refused, bad IK) → a part failure; supply
          retries it once.
        """
        aborted = isinstance(exc, Aborted)
        protective = isinstance(exc, ProtectiveStop)
        fault = (not aborted and not protective
                 and (isinstance(exc, RobotFault) or not self._backend_connected()))
        reason = ("emergency_stop" if isinstance(exc, EmergencyStop) else
                  "protective_stop" if protective else
                  "robot_fault" if fault else None)
        self.bus.publish("robot.skill_failed", {"job_id": job_id, "skill": skill, "args": args,
                                                "error": error,
                                                "protective_stop": protective,
                                                "aborted": aborted,
                                                "robot_fault": fault,
                                                "safety": reason})
        if reason is not None:
            self._latch(reason, "backend", error=error if fault else None)

    def _backend_connected(self) -> bool:
        try:
            return bool(self.backend.state().connected)
        except Exception:
            return False

    # ----------------------------------------------------------------- latch
    def latch(self, reason: str, source: str = "supply", error: str | None = None) -> bool:
        """Public latch, for callers that detect a robot fault the backend did not raise
        (SupplyController's repeated-failure circuit breaker)."""
        return self._latch(reason, source, error=error)

    def _latch(self, reason: str, source: str, error: str | None = None) -> bool:
        """Latch on a transition; publishes `robot.estop` outside the lock. Idempotent."""
        with self._lock:
            if self._latched == reason:
                return False
            self._latched = reason
        # jobs queued before the latch must not run either (they would fail identically)
        self.clear_queue()
        payload = {"reason": reason, "source": source}
        if error is not None:
            payload["error"] = error
        self.bus.publish("robot.estop", payload)
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
