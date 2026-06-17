import math

from hub.analysis.features import FEATURES, extract_features


def write(tmp_path, rows):
    p = tmp_path / "rec.csv"
    p.write_text("t_offset,signal,value\n" + "".join(f"{t},{s},{v}\n" for t, s, v in rows))
    return p


def test_feature_list():
    assert FEATURES == ["mean", "sd", "min", "max", "slope", "peaks_per_min", "auc_per_min"]


def test_mean_sd_min_max(tmp_path):
    p = write(tmp_path, [(0.0, "shimmer.gsr", 2.0), (0.1, "shimmer.gsr", 4.0), (0.2, "shimmer.gsr", 6.0)])
    f = extract_features(p, "shimmer.gsr")
    assert f["mean"] == 4.0 and f["min"] == 2.0 and f["max"] == 6.0
    assert math.isclose(f["sd"], math.sqrt(8 / 3), rel_tol=1e-9)


def test_slope_of_a_ramp(tmp_path):
    # value = 10 * t  → slope ≈ 10 per second
    p = write(tmp_path, [(t / 10, "ppg.hr", 10.0 * (t / 10)) for t in range(11)])
    f = extract_features(p, "ppg.hr")
    assert math.isclose(f["slope"], 10.0, rel_tol=1e-6)


def test_peaks_per_min_counts_local_maxima(tmp_path):
    # 3 clear peaks over 6 seconds → 30 peaks/min
    rows = []
    t = 0.0
    for _ in range(3):
        for v in (0.0, 0.0, 5.0, 0.0, 0.0):  # a spike
            rows.append((round(t, 2), "rgb.blink", v)); t += 0.4
    p = write(tmp_path, rows)
    f = extract_features(p, "rgb.blink")
    assert 2 <= f["peaks_per_min"] <= 40  # 3 peaks over ~6s; exact value sane and > 0
    assert f["peaks_per_min"] > 0


def test_absent_signal_returns_none(tmp_path):
    p = write(tmp_path, [(0.0, "shimmer.gsr", 1.0)])
    assert extract_features(p, "ppg.hr") is None


def test_slope_zero_for_single_point(tmp_path):
    p = write(tmp_path, [(0.0, "ppg.hr", 42.0)])
    f = extract_features(p, "ppg.hr")
    assert f["slope"] == 0.0


def test_peaks_zero_for_flat_signal(tmp_path):
    p = write(tmp_path, [(i * 0.4, "rgb.blink", 3.0) for i in range(10)])
    f = extract_features(p, "rgb.blink")
    assert f["peaks_per_min"] == 0.0


def test_feature_list_includes_auc():
    assert FEATURES == ["mean", "sd", "min", "max", "slope", "peaks_per_min", "auc_per_min"]


def test_auc_per_min_constant_signal(tmp_path):
    # constant 2.0 sampled over exactly 1.0 s → trapz = 2.0 (µS·s); /(1/60 min) = 120
    p = write(tmp_path, [(t / 10, "shimmer.gsr", 2.0) for t in range(11)])
    f = extract_features(p, "shimmer.gsr")
    assert math.isclose(f["auc_per_min"], 120.0, rel_tol=1e-6)


def test_auc_per_min_zero_for_single_point(tmp_path):
    p = write(tmp_path, [(0.0, "shimmer.gsr", 5.0)])
    assert extract_features(p, "shimmer.gsr")["auc_per_min"] == 0.0


def test_transform_is_applied_before_features(tmp_path):
    # transform doubling the values doubles the mean
    p = write(tmp_path, [(0.0, "ppg.hr", 2.0), (0.1, "ppg.hr", 4.0)])
    raw = extract_features(p, "ppg.hr")
    doubled = extract_features(p, "ppg.hr", transform=lambda v: v * 2)
    assert math.isclose(doubled["mean"], raw["mean"] * 2, rel_tol=1e-9)
