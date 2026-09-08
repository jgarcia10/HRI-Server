"""Executes robot skills on a dedicated worker thread and narrates them on the bus.

Bus callbacks elsewhere (TaskEngine, SupplyController) call `submit()`/`supply()` — which
only enqueue — so nobody ever blocks on robot motion inside a bus callback.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
import uuid

from .robotd.base import ProtectiveStop, RobotBackend, RobotError

log = logging.getLogger(__name__)


class RobotBridge:
    def __init__(self, bus, backend: RobotBackend, now=time.time):
        self.bus = bus
        self.backend = backend
        self.now = now
        self._q: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._idle = threading.Event()
        self._idle.set()
        self._lock = threading.Lock()
        self._active = False  # True when a job has been dequeued and not yet finished

    # -------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._thread is not None:
            return
        if not self.backend.state().connected:
            self.backend.connect()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="robot-bridge")
        self._thread.start()

    def stop(self) -> None:
        self._q.put(None)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                log.warning("RobotBridge worker thread did not exit within timeout")
            else:
                self._thread = None

    # ---------------------------------------------------------------- submit
    def submit(self, skill: str, **args) -> str:
        job_id = uuid.uuid4().hex[:8]
        with self._lock:
            self._idle.clear()
            self._q.put((job_id, skill, args))
        self.bus.publish("robot.skill_queued", {"job_id": job_id, "skill": skill, "args": args})
        return job_id

    def supply(self, part_id: str, depot_slot: str, staging_slot: str) -> str:
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
        try:
            self.backend.stop()
        finally:
            self.bus.publish("robot.estop", {})
            self._publish_state()

    def queue_size(self) -> int:
        return self._q.qsize()

    def wait_idle(self, timeout: float) -> bool:
        return self._idle.wait(timeout)

    def state(self) -> dict:
        return {**self.backend.state().as_dict(), "queue": self._q.qsize()}

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
            try:
                self._execute(skill, args, job_id)
                self.bus.publish("robot.skill_done", {"job_id": job_id, "skill": skill, "args": args,
                                                      "duration_s": round(self.now() - t0, 3)})
            except RobotError as e:
                self.bus.publish("robot.skill_failed", {"job_id": job_id, "skill": skill, "args": args,
                                                        "error": str(e),
                                                        "protective_stop": isinstance(e, ProtectiveStop)})
            except Exception as e:  # never let the worker die
                self.bus.publish("robot.skill_failed", {"job_id": job_id, "skill": skill, "args": args,
                                                        "error": f"{type(e).__name__}: {e}",
                                                        "protective_stop": False})
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

    def _publish_state(self) -> None:
        self.bus.publish("robot.state", self.state())
