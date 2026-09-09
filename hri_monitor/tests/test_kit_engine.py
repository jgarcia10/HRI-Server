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


def test_perturbation_skipped_when_fewer_than_two_parts_remain():
    eng, events, clock = make()
    eng.start_block()
    for _ in range(5):
        finish_order(eng)
        if eng.state()["phase"] == "between_orders":
            eng.next_order()
    st = eng.state()
    assert st["order_id"] == "O6" and st["kind"] == "perturbed"
    n_parts = st["n_parts"]
    for _ in range(n_parts - 1):            # place all but the last part
        eng.mark_part_placed()
    assert eng.state()["step_index"] == n_parts - 1

    # Push well past the latest possible perturbation instant (window is [0.33, 0.66]
    # of the 180s time limit, so <=118.8s) but still inside the order (<180s); tick a
    # few times to exercise the retry path.
    clock.t += 130
    for _ in range(3):
        eng.tick()
    assert eng.state()["perturbation_applied"] is False
    assert not [d for t, d in events if t == "task.perturbation"]

    eng.mark_part_placed()                  # finish the order (and the block)
    assert eng.state()["phase"] == "done"
    assert eng.state()["perturbation_applied"] is False
    assert not [d for t, d in events if t == "task.perturbation"]


def test_tick_reemits_state_outside_running():
    eng, events, clock = make()
    eng.start_block()
    finish_order(eng)                       # completes O1 -> between_orders
    assert eng.state()["phase"] == "between_orders"
    n_before = topics(events).count("task.state")
    eng.tick()
    n_after = topics(events).count("task.state")
    assert n_after == n_before + 1
    last_state = [d for t, d in events if t == "task.state"][-1]
    assert last_state["phase"] == "between_orders"
