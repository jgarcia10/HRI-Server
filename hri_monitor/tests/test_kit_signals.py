from hub.experiments.signals import RECORDED_TOPICS, sample_rows


def test_task_topics_recorded():
    assert {"task.countdown", "task.step", "task.order_started", "task.part_placed",
            "task.perturbation", "wizard.reposition", "wizard.speech"} <= RECORDED_TOPICS


def test_sample_rows_task():
    assert sample_rows("task.countdown", {"order_id": "O3", "remaining_s": 42.5}) == \
        [("task.remaining_s", 42.5)]
    assert sample_rows("task.step", {"order_id": "O3", "step_index": 3, "part_id": "x"}) == \
        [("task.step_index", 3.0)]
    assert sample_rows("task.order_started", {"order_id": "O3", "order_index": 2,
                                              "kind": "rush", "n_parts": 9,
                                              "time_limit_s": 150}) == \
        [("task.order_index", 2.0)]
    assert sample_rows("task.part_placed", {"order_id": "O3", "step_index": 0,
                                            "part_id": "O3P1"}) == [("task.part_placed", 1.0)]
    assert sample_rows("wizard.reposition", {"slot": "L"}) == [("wizard.reposition", 1.0)]


def test_task_state_not_recorded():
    assert "task.state" not in RECORDED_TOPICS
    assert sample_rows("task.state", {"phase": "running"}) == []
