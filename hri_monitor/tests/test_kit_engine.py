import random

from hub.bus import MessageBus
from hub.kit_study.orders import load_block
from hub.kit_study.task_engine import TaskEngine

F1 = "hub/kit_study/configs/orders_f1.yaml"


class Clock:
    def __init__(self):
        self.t = 1000.0
    def __call__(self):
        return self.t


def make(seed=7):
    bus = MessageBus()
    events = []
    bus.subscribe("*", lambda m: events.append((m["topic"], m["data"])))
    clock = Clock()
    eng = TaskEngine(bus, load_block(F1), now=clock, rng=random.Random(seed))
    return eng, events, clock


def topics(events):
    return [t for t, _ in events]


def finish_order(eng):
    for _ in range(eng.state()["n_parts"] - eng.state()["step_index"]):
        eng.mark_part_placed()


def test_full_block_walkthrough():
    eng, events, clock = make()
    eng.start_block()
    assert eng.state()["phase"] == "running"
    assert eng.state()["order_id"] == "O1"
    for i in range(6):
        finish_order(eng)
        st = eng.state()
        assert st["phase"] in ("between_orders", "done")
        if i < 5:
            eng.next_order()
    assert eng.state()["phase"] == "done"
    ts = topics(events)
    assert ts.count("task.order_started") == 6
    assert ts.count("task.order_completed") == 6
    assert "task.block_completed" in ts


def test_countdown_and_timeout():
    eng, events, clock = make()
    eng.start_block()
    for _ in range(2):          # O1, O2 (untimed)
        finish_order(eng)
        eng.next_order()
    assert eng.state()["order_id"] == "O3"
    clock.t += 10
    eng.tick()
    cd = [d for t, d in events if t == "task.countdown"]
    assert cd and abs(cd[-1]["remaining_s"] - 140.0) < 1e-6
    clock.t += 141
    eng.tick()
    done = [d for t, d in events if t == "task.order_completed"][-1]
    assert done["order_id"] == "O3" and done["timed_out"] is True
    assert eng.state()["phase"] == "between_orders"


def test_perturbation_fires_once_inside_window():
    eng, events, clock = make()
    eng.start_block()
    for _ in range(5):
        finish_order(eng)
        if eng.state()["phase"] == "between_orders":
            eng.next_order()
    st = eng.state()
    assert st["order_id"] == "O6" and st["kind"] == "perturbed"
    limit = 180.0
    for _ in range(int(limit)):
        clock.t += 1
        eng.tick()
        if eng.state()["perturbation_applied"]:
            break
    perts = [d for t, d in events if t == "task.perturbation"]
    assert len(perts) == 1
    frac = (clock.t - perts[0]["order_started_ts"]) / limit
    assert 0.33 <= frac <= 0.67
    a, b = perts[0]["swap"]
    assert a != b


def test_part_placed_before_start_is_ignored():
    eng, events, _ = make()
    eng.mark_part_placed()      # no crash, no events
    assert eng.state()["phase"] == "idle"
