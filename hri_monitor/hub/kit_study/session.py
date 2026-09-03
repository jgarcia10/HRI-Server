"""Experiment session: wires TaskEngine to the recording pipeline and markers."""
from __future__ import annotations

import random
import threading
import time
from pathlib import Path

from .orders import load_block
from .task_engine import TaskEngine

EXPERIMENT_NAME = "Kit Study"
CONDITIONS = ("C0", "C1")
_MARKER_TOPICS = {"task.order_started", "task.perturbation",
                  "task.order_completed", "task.block_completed",
                  "wizard.speech", "wizard.reposition"}
_CONFIGS_DIR = Path(__file__).parent / "configs"
_SPEECH_LABEL_MAX = 120


def _idle_task_state(block) -> dict:
    """Full-shape task.state for a torn-down session (matches KitTaskState on the UI)."""
    return {
        "phase": "idle",
        "order_index": -1,
        "order_id": None,
        "kind": None,
        "step_index": 0,
        "n_parts": 0,
        "current_part": None,
        "remaining_s": None,
        "queue": [o.kind for o in block.orders] if block is not None else [],
        "perturbation_applied": False,
    }


class KitSession:
    def __init__(self, bus, db, controller, configs_dir=None, now=time.time, tick_interval=1.0):
        self.bus = bus
        self.db = db
        self.controller = controller
        self.configs_dir = Path(configs_dir) if configs_dir else _CONFIGS_DIR
        self.now = now
        self.tick_interval = tick_interval
        self.engine: TaskEngine | None = None
        self._info = None
        self._ticker = None
        self._stop_evt = threading.Event()

    # ---------------------------------------------------------------- public
    def start(self, participant_code: str, condition: str, block: str) -> dict:
        if self._info is not None:
            raise RuntimeError("a kit session is already active")
        if condition not in CONDITIONS:
            raise ValueError(f"condition must be one of {CONDITIONS}")
        block_path = self.configs_dir / Path(block).name
        spec = load_block(block_path)
        exp_id = self._ensure_experiment()
        cond_id = self._condition_id(exp_id, condition)
        part_id = self._ensure_participant(exp_id, participant_code)
        rec = self.controller.start(condition_id=cond_id, experiment_id=exp_id,
                                    participant_id=part_id)
        try:
            self.bus.subscribe("*", self._on_bus)
            self.engine = TaskEngine(self.bus, spec, now=self.now, rng=random.Random())
            self.engine.start_block()
            self._stop_evt.clear()
            self._ticker = threading.Thread(target=self._tick_loop, daemon=True)
            self._ticker.start()
        except Exception:
            # clean up: unsubscribe, stop recording, reset engine
            self.bus.unsubscribe("*", self._on_bus)
            self.controller.stop()
            self.engine = None
            raise
        self._info = {**rec, "condition": condition, "participant": participant_code,
                      "block": spec.family}
        self.bus.publish("task.session", dict(self._info))
        return dict(self._info)

    def stop(self):
        if self._info is None:
            return None
        self._stop_evt.set()
        if self._ticker is not None:
            self._ticker.join(timeout=2.0)
        self.engine.stop()
        self.bus.unsubscribe("*", self._on_bus)
        block = self.engine.block
        status = self.controller.status()
        if status is not None and status["recording_id"] == self._info["recording_id"]:
            # Only stop the recording if it's still ours: an external stop (or a new
            # recording started after that) must not be torn down by our teardown.
            out = self.controller.stop()
        else:
            out = None
        info, self._info, self.engine = self._info, None, None
        self.bus.publish("task.state", _idle_task_state(block))
        return {**(out or {}), "condition": info["condition"]}

    def status(self):
        if self._info is None:
            return None
        return {**self._info, "task": self.engine.state()}

    # --------------------------------------------------------------- private
    def _tick_loop(self):
        while not self._stop_evt.wait(self.tick_interval):
            self.engine.tick()

    def _on_bus(self, message):
        topic = message["topic"]
        if topic not in _MARKER_TOPICS:
            return
        data = message["data"]
        if topic == "wizard.speech":
            text = str(data.get("text", ""))[:_SPEECH_LABEL_MAX]
            label = f"speech:{text}"
        elif topic == "wizard.reposition":
            label = f"reposition:{data.get('slot', '?')}"
        else:
            prefix = topic.removeprefix("task.")
            oid = data.get("order_id") or data.get("family", "")
            label = f"{prefix}:{oid}"
        try:
            self.controller.marker(label, source="kit")
        except RuntimeError:
            pass  # recording already stopped

    def _ensure_experiment(self) -> int:
        for e in self.db.list_experiments():
            if e["name"] == EXPERIMENT_NAME:
                names = [c["name"] for c in self.db.get_experiment(e["id"])["conditions"]]
                if names != list(CONDITIONS):
                    raise RuntimeError(f"experiment '{EXPERIMENT_NAME}' exists with "
                                       f"conditions {names}; expected {list(CONDITIONS)}")
                return e["id"]
        exp_id = self.db.create_experiment(EXPERIMENT_NAME,
                                           "Homeostatic-allostatic kit assembly study")
        self.db.set_conditions(exp_id, list(CONDITIONS))
        return exp_id

    def _condition_id(self, exp_id: int, name: str) -> int:
        for c in self.db.get_experiment(exp_id)["conditions"]:
            if c["name"] == name:
                return c["id"]
        raise RuntimeError(f"condition {name} not found")

    def _ensure_participant(self, exp_id: int, code: str) -> int:
        for p in self.db.list_participants(exp_id):
            if p["code"] == code:
                return p["id"]
        return self.db.create_participant(exp_id, code, "")
