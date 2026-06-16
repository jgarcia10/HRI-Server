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
    }
