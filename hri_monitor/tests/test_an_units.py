from hub.analysis.units import plot_title, y_axis_label


def test_raw_units_per_feature():
    assert y_axis_label("shimmer.gsr", "mean", "none") == "GSR (µS)"
    assert y_axis_label("thermal.forehead", "mean", "none") == "Forehead (°C)"
    assert y_axis_label("rgb.blink", "mean", "none") == "Blink (/min)"
    assert y_axis_label("shimmer.gsr", "slope", "none") == "GSR (µS/s)"
    assert y_axis_label("shimmer.gsr", "peaks_per_min", "none") == "GSR (peaks/min)"
    assert y_axis_label("shimmer.gsr", "auc_per_min", "none") == "GSR (µS·s/min)"


def test_normalized_labels_drop_units():
    assert y_axis_label("shimmer.gsr", "mean", "range") == "GSR (normalized 0-1)"
    assert y_axis_label("shimmer.gsr", "mean", "zscore") == "GSR (z-score)"


def test_plot_title_is_human():
    assert plot_title("shimmer.gsr", "mean") == "Mean GSR by condition"
    assert plot_title("shimmer.gsr", "auc_per_min") == "Cumulative AUC/min GSR by condition"
