import time

from anima.llm.backend import MockBackend

from hub.bus import MessageBus
from hub.experiments.signals import RECORDED_TOPICS, sample_rows
from hub.kit_study.anima_llm import AnimaLLM


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
