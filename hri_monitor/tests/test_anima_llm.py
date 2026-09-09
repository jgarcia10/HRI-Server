import threading
import time

from anima.llm.backend import MockBackend
from anima.llm.schema import Usage

from hub.bus import MessageBus
from hub.experiments.signals import RECORDED_TOPICS, sample_rows
from hub.kit_study.anima_llm import AnimaLLM


class BlockingBackend:
    """Fake backend whose `structured()` blocks on an Event until the test releases it,
    so tests can control exactly when an in-flight perceive/judge call "returns"."""

    def __init__(self):
        self.usage = Usage()
        self.entered = threading.Event()
        self.release = threading.Event()

    def structured(self, system, prompt, schema, *, max_tokens=1024, effort="low", salt=""):
        self.entered.set()
        self.release.wait(timeout=5.0)
        props = schema.get("properties", {})
        if "mission_score" in props:  # judge
            return {"mission_score": 0.8, "rationale": "blocked judge"}
        from anima.config import DRIVE_NAMES  # perceive
        out = {f"{n}_pull": 0.5 for n in DRIVE_NAMES}
        out.update(regime="supportive", regime_confidence=0.9, intensity=0.5,
                    rationale="blocked perception")
        return out

    def text(self, system, prompt, *, max_tokens=512, effort="low", salt=""):
        return "ok"


def make(judge_every=2):
    bus = MessageBus(); events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    a = AnimaLLM(bus, MockBackend(), mission="supply kit parts", judge_every=judge_every)
    a.start()
    return bus, events, a


def wait_for(events, topic, n=1, timeout=3.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if sum(1 for t, _ in events if t == topic) >= n:
            return True
        time.sleep(0.01)
    return False


def test_speech_triggers_perception_with_full_payload():
    bus, events, a = make()
    bus.publish("robot.part_staged", {"part_id": "F1O1P1", "slot": "L", "depot_slot": "BL1", "job_id": "j"})
    bus.publish("wizard.speech", {"text": "thanks, that is perfect"})
    assert wait_for(events, "anima.perception")
    p = next(d for t, d in events if t == "anima.perception")
    assert set(p) >= {"relatedness_pull", "competence_pull", "autonomy_pull", "resource_pull",
                      "regime", "regime_confidence", "intensity"}
    assert 0.0 <= p["intensity"] <= 1.0 and p["regime"] in ("supportive", "adversarial", "exploratory")
    a.stop()


def test_judge_runs_every_n_human_turns():
    bus, events, a = make(judge_every=2)
    bus.publish("wizard.speech", {"text": "wait"})
    bus.publish("wizard.speech", {"text": "this is useless, stop"})
    assert wait_for(events, "anima.verdict", 1)
    v = next(d for t, d in events if t == "anima.verdict")
    assert v["g"] <= 0.0
    assert a.status()["human_turns"] == 2 and a.status()["judgements"] == 1
    a.stop()


def test_reset_clears_turns_and_signals():
    bus, events, a = make()
    bus.publish("wizard.speech", {"text": "hi"})
    assert wait_for(events, "anima.perception")
    a.reset()
    assert a.status()["turns"] == 0
    a.stop()
    assert {"anima.perception", "anima.verdict"} <= RECORDED_TOPICS
    rows = dict(sample_rows("anima.perception", {"relatedness_pull": 0.8, "competence_pull": 0.5,
                                                  "autonomy_pull": 0.3, "resource_pull": 0.7,
                                                  "regime": "adversarial", "regime_confidence": 0.9,
                                                  "intensity": 0.6, "rationale": "x"}))
    assert rows["anima.relatedness_pull"] == 0.8 and rows["anima.regime_idx"] == 1.0 and rows["anima.intensity"] == 0.6
    assert sample_rows("anima.verdict", {"g": -0.2, "rationale": "x"}) == [("anima.g", -0.2)]


def test_reset_discards_in_flight_job_result():
    bus = MessageBus(); events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    backend = BlockingBackend()
    a = AnimaLLM(bus, backend, mission="supply kit parts")
    a.start()
    try:
        bus.publish("wizard.speech", {"text": "hi"})
        # Wait for the worker to actually enter the (blocking) backend call, i.e. the
        # job is genuinely in flight, not merely sitting in the queue.
        assert backend.entered.wait(timeout=3.0)
        a.reset()
        backend.release.set()  # let the stale in-flight call "return" now
        # Give the worker a chance to process the (now-stale) result.
        time.sleep(0.3)
        assert not any(t == "anima.perception" for t, _ in events)
        assert a.status()["turns"] == 0
    finally:
        a.stop()


def test_reset_drops_queued_but_not_started_job():
    bus = MessageBus(); events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    backend = BlockingBackend()
    a = AnimaLLM(bus, backend, mission="supply kit parts")
    a.start()
    try:
        # First speech enters the blocking backend call, occupying the worker thread.
        bus.publish("wizard.speech", {"text": "hi"})
        assert backend.entered.wait(timeout=3.0)
        # Second speech's job sits queued behind the first — never started.
        bus.publish("wizard.speech", {"text": "still here"})
        a.reset()
        backend.release.set()  # release the first (stale, in-flight) call
        time.sleep(0.3)
        # Neither the discarded in-flight job nor the drained queued jobs (the second
        # speech also enqueued a judge job, judge_every=2) publish anything.
        assert not any(t in ("anima.perception", "anima.verdict") for t, _ in events)
        assert a.status()["turns"] == 0 and a.status()["judgements"] == 0
    finally:
        a.stop()


def test_reset_drain_keeps_stop_sentinel_and_fresh_jobs():
    # Worker not started: exercise the drain directly. If reset() swallowed the None
    # sentinel from stop(), an idle worker blocked in get() would never exit.
    a = AnimaLLM(MessageBus(), BlockingBackend(), mission="supply kit parts")
    stale_epoch = a._epoch
    a._q.put(("perceive", stale_epoch, "stale"))
    a._q.put(None)
    a._q.put(("perceive", stale_epoch + 1, "fresh"))
    a.reset()
    left = []
    while not a._q.empty():
        left.append(a._q.get_nowait())
    assert left == [None, ("perceive", stale_epoch + 1, "fresh")]


def test_normal_job_after_reset_still_publishes():
    bus, events, a = make()
    bus.publish("wizard.speech", {"text": "hi"})
    assert wait_for(events, "anima.perception")
    a.reset()
    events.clear()
    bus.publish("wizard.speech", {"text": "thanks, that is perfect"})
    assert wait_for(events, "anima.perception")
    assert a.status()["turns"] == 1
    a.stop()
