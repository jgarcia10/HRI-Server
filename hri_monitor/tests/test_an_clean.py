import numpy as np

from hub.analysis.clean import clean, clean_values


def test_drops_non_finite_for_any_signal():
    vs = clean_values("shimmer.ppg", np.array([1.0, np.nan, 2.0, np.inf, -np.inf, 3.0]))
    assert list(vs) == [1.0, 2.0, 3.0]


def test_gsr_drops_negatives_keeps_zero():
    vs = clean_values("shimmer.gsr", np.array([-5.0, 0.0, 2.0, -0.1, 4.0]))
    assert list(vs) == [0.0, 2.0, 4.0]


def test_hr_drops_zero_and_negative():
    vs = clean_values("ppg.hr", np.array([0.0, -3.0, 60.0, 72.0]))
    assert list(vs) == [60.0, 72.0]


def test_thermal_bounds():
    vs = clean_values("thermal.forehead", np.array([5.0, 10.0, 33.0, 45.0, 50.0, -1.0]))
    assert list(vs) == [10.0, 33.0, 45.0]


def test_other_signal_only_finite():
    vs = clean_values("rgb.blink", np.array([-2.0, 0.0, 5.0, np.nan]))
    assert list(vs) == [-2.0, 0.0, 5.0]  # negatives allowed for non-bounded signals


def test_clean_filters_ts_and_vs_together():
    ts = np.array([0.0, 0.1, 0.2, 0.3])
    vs = np.array([1.0, -1.0, np.nan, 4.0])  # indices 1 (neg gsr) and 2 (nan) dropped
    ct, cv = clean("shimmer.gsr", ts, vs)
    assert list(ct) == [0.0, 0.3] and list(cv) == [1.0, 4.0]


def test_clean_drops_non_finite_timestamp():
    ts = np.array([0.0, np.nan, 0.2])
    vs = np.array([1.0, 2.0, 3.0])
    ct, cv = clean("shimmer.gsr", ts, vs)
    assert list(ct) == [0.0, 0.2] and list(cv) == [1.0, 3.0]
