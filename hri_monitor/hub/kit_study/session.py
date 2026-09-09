"""Experiment session: wires TaskEngine to the recording pipeline and markers."""
from __future__ import annotations

import logging
import random
import threading
import time
from pathlib import Path

from . import questionnaires as q13s
from .orders import load_block
from .task_engine import TaskEngine

EXPERIMENT_NAME = "Kit Study"
CONDITIONS = ("C0", "C1")
_MARKER_TOPICS = {"task.order_started", "task.perturbation",
                  "task.order_completed", "task.block_completed",
                  "wizard.speech", "wizard.reposition", "wizard.mat_cleared",
                  # I5: without these, which part went to which slot (and why the robot
                  # stopped) is unrecoverable from a recording.
                  "robot.part_staged", "robot.skill_failed", "robot.estop",
                  "robot.rejected", "robot.resumed",
                  "supply.decision", "supply.blocked"}
# Session teardown waits for the in-flight robot job (I3). A measured URSim supply cycle is
# ~22 s (lab cycles are <= 5 s), so 6 s used to log a false "robot still busy" and let the
# job's robot.part_staged land in the next session. Start-while-busy still 409s.
_STOP_WAIT_S = 25.0
_CONFIGS_DIR = Path(__file__).parent / "configs"
_SPEECH_LABEL_MAX = 120

log = logging.getLogger(__name__)


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
    def __init__(self, bus, db, controller, configs_dir=None, now=time.time, tick_interval=1.0,
                 bridge=None, default_profile: dict | None = None):
        self.bus = bus
        self.db = db
        self.controller = controller
        self.configs_dir = Path(configs_dir) if configs_dir else _CONFIGS_DIR
        self.now = now
        self.tick_interval = tick_interval
        self.bridge = bridge
        self.default_profile = default_profile
        self.supply = None
        self.engine: TaskEngine | None = None
        self.anima_llm = None
        self._info = None
        self._ticker = None
        self._stop_evt = threading.Event()
        # Post-block questionnaires: set when a block stops, cleared when both instruments are
        # answered (or the wizard skips). The next block cannot start while it is pending, so
        # no condition ends up without its NASA-TLX / trust answers by accident.
        self._pending_q: dict | None = None
        self._last_q: dict | None = None

    # ---------------------------------------------------------------- public
    def start(self, participant_code: str, condition: str, block: str,
              profile: dict | None = None) -> dict:
        if self._info is not None:
            raise RuntimeError("a kit session is already active")
        if self._pending_q is not None:
            raise RuntimeError("questionnaires pending: the participant has not answered the "
                               f"post-block questionnaires for {self._pending_q['participant']} / "
                               f"{self._pending_q['condition']} yet (answer them on the participant "
                               "screen, or skip them from the wizard)")
        if self.bridge is not None and (self.bridge.queue_size() or self.bridge.busy()):
            # I3: a job left over from the previous session would stage a part into this one
            raise RuntimeError("robot busy: a previous robot job is still running — "
                               "wait for it to finish (or press STOP) before starting a session")
        if condition not in CONDITIONS:
            raise ValueError(f"condition must be one of {CONDITIONS}")
        block_path = self.configs_dir / Path(block).name
        spec = load_block(block_path)
        exp_id = self._ensure_experiment()
        cond_id = self._condition_id(exp_id, condition)
        part_id = self._ensure_participant(exp_id, participant_code)
        rec = self.controller.start(condition_id=cond_id, experiment_id=exp_id,
                                    participant_id=part_id)
        if self.anima_llm:
            self.anima_llm.reset()
        try:
            self.bus.subscribe("*", self._on_bus)
            self.engine = TaskEngine(self.bus, spec, now=self.now, rng=random.Random())
            if self.bridge is not None:
                from .supply import SupplyController, SupplyProfile
                prof = SupplyProfile(**{**(self.default_profile or {}), **(profile or {})})
                self.supply = SupplyController(self.bus, self.bridge, spec, prof)
                self.supply.start()
            self.engine.start_block()
            self._stop_evt.clear()
            self._ticker = threading.Thread(target=self._tick_loop, daemon=True)
            self._ticker.start()
        except Exception:
            # clean up: unsubscribe, stop recording, reset engine
            self.bus.unsubscribe("*", self._on_bus)
            if self.supply is not None:
                self.supply.stop()
                self.supply = None
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
        if self.supply is not None:
            self.supply.stop()
            self.supply = None
        if self.bridge is not None:
            # a stopped session must never leave supply jobs moving the robot, and its
            # robot.part_staged must not land in the next session (I3)
            self.bridge.clear_queue()
            if not self.bridge.wait_idle(_STOP_WAIT_S):
                log.warning("robot still busy %.0fs after session stop; the in-flight job was "
                            "not cancelled", _STOP_WAIT_S)
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
        self._open_questionnaires(info)
        return {**(out or {}), "condition": info["condition"]}

    def status(self):
        if self._info is None:
            return None
        return {**self._info, "task": self.engine.state(),
                "supply": self.supply.status() if self.supply else None,
                "anima": self.anima_llm.status() if self.anima_llm else None}

    # ------------------------------------------------------- questionnaires
    def questionnaire_state(self) -> dict:
        """Streamed as `kit.questionnaire`; the participant screen renders the pending one."""
        if self._pending_q is not None:
            return {"status": "pending", **self._pending_q,
                    "instruments": q13s.INSTRUMENTS, "order": list(q13s.ORDER)}
        if self._last_q is not None:
            return {"status": "done", **self._last_q}
        return {"status": "none"}

    def submit_questionnaire(self, instrument: str, answers: dict) -> dict:
        if self._pending_q is None:
            raise RuntimeError("no questionnaire pending")
        if self._pending_q["done"].get(instrument):
            raise RuntimeError(f"{instrument} already answered for this block")
        clean = q13s.validate(instrument, answers)
        sc = q13s.score(instrument, clean)
        self.db.add_questionnaire(self._pending_q["session_id"], self._pending_q["condition_id"],
                                  instrument, clean, sc, self._pending_q.get("recording_id"))
        self._pending_q["done"][instrument] = sc
        self._pending_q["next"] = next((i for i in q13s.ORDER if not self._pending_q["done"].get(i)),
                                       None)
        self.bus.publish("kit.questionnaire_answered", {"instrument": instrument, "score": sc,
                                                        **{k: self._pending_q[k] for k in
                                                           ("participant", "condition", "session_id")}})
        if self._pending_q["next"] is None:
            self._close_questionnaires("completed")
        self._publish_q()
        return self.questionnaire_state()

    def skip_questionnaires(self, reason: str = "skipped by wizard") -> dict:
        if self._pending_q is None:
            return self.questionnaire_state()
        for instrument in q13s.ORDER:
            if not self._pending_q["done"].get(instrument):
                self.db.add_questionnaire(self._pending_q["session_id"],
                                          self._pending_q["condition_id"], instrument,
                                          {"skipped": reason}, None,
                                          self._pending_q.get("recording_id"))
        self._close_questionnaires("skipped")
        self._publish_q()
        return self.questionnaire_state()

    def _open_questionnaires(self, info: dict) -> None:
        exp_id = self._ensure_experiment()
        self._pending_q = {"session_id": info["session_id"], "recording_id": info.get("recording_id"),
                           "condition_id": self._condition_id(exp_id, info["condition"]),
                           "participant": info["participant"], "condition": info["condition"],
                           "block": info.get("block"), "done": {}, "next": q13s.ORDER[0]}
        self._publish_q()

    def _close_questionnaires(self, outcome: str) -> None:
        p = self._pending_q
        self._last_q = {"participant": p["participant"], "condition": p["condition"],
                        "session_id": p["session_id"], "done": dict(p["done"]), "outcome": outcome}
        self._pending_q = None

    def _publish_q(self) -> None:
        self.bus.publish("kit.questionnaire", self.questionnaire_state())

    def list_questionnaires(self, instrument: str | None = None) -> list[dict]:
        exp = next((e for e in self.db.list_experiments() if e["name"] == EXPERIMENT_NAME), None)
        if exp is None:
            return []
        return self.db.list_questionnaires(exp["id"], instrument)

    # --------------------------------------------------------------- private
    def _tick_loop(self):
        while not self._stop_evt.wait(self.tick_interval):
            self.engine.tick()

    def _on_bus(self, message):
        topic = message["topic"]
        if topic not in _MARKER_TOPICS:
            return
        data = message["data"] or {}
        if topic == "wizard.speech":
            text = str(data.get("text", ""))[:_SPEECH_LABEL_MAX]
            label = f"speech:{text}"
        elif topic == "wizard.reposition":
            label = f"reposition:{data.get('slot', '?')}"
        elif topic == "wizard.mat_cleared":
            label = "mat_cleared"
        elif topic == "robot.part_staged":
            label = f"staged:{data.get('part_id')}@{data.get('slot')}"
        elif topic == "robot.skill_failed":
            kind = ("aborted" if data.get("aborted") else
                    data.get("safety") or
                    ("protective_stop" if data.get("protective_stop") else "error"))
            pid = (data.get("args") or {}).get("part_id") or ""
            label = f"skill_failed:{data.get('skill')}:{pid}:{kind}"
        elif topic == "robot.estop":
            label = f"estop:{data.get('reason', 'estop')}:{data.get('source', '?')}"
        elif topic == "robot.rejected":
            label = f"rejected:{data.get('skill')}:{data.get('reason')}"
        elif topic == "robot.resumed":
            label = "resumed"
        elif topic == "supply.decision":
            label = f"decision:{data.get('reason')}:{data.get('part_id')}@{data.get('slot')}"
        elif topic == "supply.blocked":
            label = f"blocked:{data.get('reason')}:{data.get('needed')}"
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
