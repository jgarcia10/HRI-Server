from hub.experiments.signals import RECORDED_TOPICS, sample_rows


def test_scalar_topics_map_to_one_row():
    assert sample_rows("shimmer.gsr", {"value": 4.21}) == [("shimmer.gsr", 4.21)]
    assert sample_rows("ppg.hr", {"value": 72.0}) == [("ppg.hr", 72.0)]
    assert sample_rows("rgb.blink", {"rate": 17.2, "ear": 0.3}) == [("rgb.blink", 17.2)]


def test_thermal_temps_expands_to_four_rows():
    rows = sample_rows("thermal.temps",
                       {"forehead": 34.5, "left_cheek": 33.8, "right_cheek": 33.9, "nose": 32.5})
    assert ("thermal.forehead", 34.5) in rows
    assert ("thermal.left_cheek", 33.8) in rows
    assert len(rows) == 4


def test_model_estimates_expands_to_two_rows():
    rows = sample_rows("model.estimates", {"cognitive_load": 0.4, "trust": 0.7})
    assert set(rows) == {("model.cognitive_load", 0.4), ("model.trust", 0.7)}


def test_unknown_topic_yields_nothing():
    assert sample_rows("device.status", {"device": "rgb", "status": "connected"}) == []


def test_recorded_topics_set():
    assert RECORDED_TOPICS == {
        "shimmer.gsr", "shimmer.ppg", "ppg.hr", "ppg.hrv",
        "rgb.blink", "thermal.temps", "model.estimates",
        "task.countdown", "task.step", "task.order_started",
        "task.part_placed", "task.perturbation",
        "wizard.reposition", "wizard.speech", "wizard.request_part", "wizard.slot_cleared",
        "wizard.mat_cleared",
        "robot.skill_done", "robot.part_staged", "robot.skill_failed", "robot.estop",
        "robot.rejected", "robot.resumed",
        "supply.decision", "supply.blocked",
        "anima.perception", "anima.verdict", "anima.error",
    }


def test_skill_done_is_one_series_per_skill():
    """I4: mixing set_pace/home/supply durations makes the M4 supply-cycle p95 uncomputable."""
    assert sample_rows("robot.skill_done", {"skill": "supply", "duration_s": 4.2}) == \
        [("robot.supply_duration_s", 4.2)]
    assert sample_rows("robot.skill_done", {"skill": "home", "duration_s": 3.0}) == \
        [("robot.home_duration_s", 3.0)]


def test_mat_cleared_is_an_impulse():
    """C5: the mat sweep frees every slot — without it in the CSV a supply gap around an
    order transition is unexplainable."""
    assert sample_rows("wizard.mat_cleared", {}) == [("wizard.mat_cleared", 1.0)]
    assert sample_rows("wizard.slot_cleared", {"slot": "L"}) == [("wizard.slot_cleared", 1.0)]


def test_robot_latch_topics_are_impulses():
    assert sample_rows("robot.rejected", {"skill": "supply", "args": {}, "reason": "estop"}) == \
        [("robot.rejected", 1.0)]
    assert sample_rows("robot.resumed", {}) == [("robot.resumed", 1.0)]
    assert sample_rows("anima.error", {"kind": "perception", "error": "boom"}) == [("anima.error", 1.0)]
