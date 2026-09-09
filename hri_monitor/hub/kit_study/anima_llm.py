"""Cristi's ANIMA language shell (perception + judge) running inside the hub.

Human turns = wizard speech (later ASR). Agent turns = what the robot did/said, rendered as
text so the judge sees the collaboration, not only words. Both LLM calls run on a worker
thread — bus callbacks only enqueue. The judge is off the critical path (metrics + future
meta-reward), exactly as anima/docs/pipeline.md prescribes.
"""
from __future__ import annotations

import queue
import threading

from anima.config import DRIVE_NAMES
from anima.llm.judge import judge
from anima.llm.perception import perceive
from anima.llm.schema import Turn


class AnimaLLM:
    _TOPICS = ("wizard.speech", "robot.part_staged", "supply.decision", "task.order_started")

    def __init__(self, bus, backend, mission: str, judge_every: int = 2, history: int = 6):
        self.bus = bus
        self.backend = backend
        self.mission = mission
        self.judge_every = max(1, int(judge_every))
        self.history = int(history)
        self._turns: list[Turn] = []
        self._lock = threading.Lock()
        self._q: queue.Queue = queue.Queue()
        self._thread = None
        self._stop = threading.Event()
        self._human_turns = 0
        self._judgements = 0
        self._errors = 0
        self._epoch = 0

    # -------------------------------------------------------------- lifecycle
    def start(self) -> None:
        for t in self._TOPICS:
            self.bus.subscribe(t, self._on_bus)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="anima-llm")
        self._thread.start()

    def stop(self) -> None:
        for t in self._TOPICS:
            self.bus.unsubscribe(t, self._on_bus)
        self._stop.set(); self._q.put(None)
        if self._thread is not None:
            self._thread.join(timeout=3.0); self._thread = None

    def reset(self) -> None:
        with self._lock:
            self._epoch += 1
            epoch = self._epoch
            self._turns.clear(); self._human_turns = 0; self._judgements = 0
        # Drop any jobs enqueued before this reset (they carry the stale epoch); keep
        # anything concurrently enqueued under the new epoch. In-flight jobs (already
        # dequeued by the worker) are caught by the epoch re-check in `_loop`.
        pending = []
        try:
            while True:
                item = self._q.get_nowait()
                if item is not None and item[1] == epoch:
                    pending.append(item)
        except queue.Empty:
            pass
        for item in pending:
            self._q.put(item)

    def status(self) -> dict:
        with self._lock:
            return {"turns": len(self._turns), "human_turns": self._human_turns,
                    "judgements": self._judgements, "errors": self._errors,
                    "usage": self.backend.usage.summary()}

    # ----------------------------------------------------------------- events
    def _on_bus(self, message) -> None:
        topic, d = message["topic"], message["data"]
        if topic == "wizard.speech":
            with self._lock:
                self._turns.append(Turn("human", str(d.get("text", ""))))
                self._human_turns += 1
                do_judge = self._human_turns % self.judge_every == 0
                epoch = self._epoch
            self._q.put(("perceive", epoch))
            if do_judge:
                self._q.put(("judge", epoch))
        elif topic == "robot.part_staged":
            self._agent(f"[robot] staged part {d.get('part_id')} in slot {d.get('slot')}")
        elif topic == "supply.decision":
            self._agent(f"[robot] decided to bring {d.get('part_id')} to {d.get('slot')} ({d.get('reason')})")
        elif topic == "task.order_started":
            self._agent(f"[task] order {d.get('order_id')} ({d.get('kind')}, {d.get('n_parts')} parts) started")

    def _agent(self, text: str) -> None:
        with self._lock:
            self._turns.append(Turn("agent", text))

    # ----------------------------------------------------------------- worker
    def _loop(self) -> None:
        while not self._stop.is_set():
            item = self._q.get()
            if item is None:
                break
            kind, epoch = item
            with self._lock:
                if epoch != self._epoch:
                    continue  # reset() happened before this job started: drop it
                turns = list(self._turns)
            try:
                if kind == "perceive":
                    p = perceive(self.backend, turns, self.mission, history=self.history)
                    with self._lock:
                        if epoch != self._epoch:
                            continue  # reset() happened mid-call: discard the result
                    payload = {f"{n}_pull": float(v) for n, v in zip(DRIVE_NAMES, p.drive_pull)}
                    payload.update(regime=p.regime_argmax,
                                   regime_confidence=float(p.regime_posterior.max()),
                                   intensity=float(p.intensity), rationale=p.rationale)
                    self.bus.publish("anima.perception", payload)
                else:
                    v = judge(self.backend, turns, self.mission, history=self.history + 2)
                    with self._lock:
                        if epoch != self._epoch:
                            continue  # reset() happened mid-call: discard the result
                        self._judgements += 1
                    self.bus.publish("anima.verdict", {"g": float(v.g), "rationale": v.rationale})
            except Exception as e:  # LLM/network failures never take the app down
                with self._lock:
                    if epoch != self._epoch:
                        continue  # stale job: don't record an error for a discarded reset
                    self._errors += 1
                self.bus.publish("anima.error", {"kind": kind, "error": f"{type(e).__name__}: {e}"})
