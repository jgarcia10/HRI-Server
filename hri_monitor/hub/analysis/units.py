"""Display units + labels for analysis plots (y-axis + title)."""

SIGNAL_UNITS = {
    "shimmer.gsr": "µS", "shimmer.ppg": "mV", "ppg.hr": "bpm", "ppg.hrv": "ms",
    "rgb.blink": "/min", "thermal.forehead": "°C", "thermal.left_cheek": "°C",
    "thermal.right_cheek": "°C", "thermal.nose": "°C",
}
SIGNAL_SHORT = {
    "shimmer.gsr": "GSR", "shimmer.ppg": "PPG", "ppg.hr": "HR", "ppg.hrv": "HRV",
    "rgb.blink": "Blink", "thermal.forehead": "Forehead", "thermal.left_cheek": "L cheek",
    "thermal.right_cheek": "R cheek", "thermal.nose": "Nose",
}
FEATURE_LABELS = {
    "mean": "Mean", "sd": "SD", "min": "Min", "max": "Max",
    "slope": "Slope", "peaks_per_min": "Peaks/min", "auc_per_min": "Cumulative AUC/min",
}


def y_axis_label(signal, feature, normalize="none"):
    short = SIGNAL_SHORT.get(signal, signal)
    if normalize == "range":
        return f"{short} (normalized 0-1)"
    if normalize == "zscore":
        return f"{short} (z-score)"
    unit = SIGNAL_UNITS.get(signal, "")
    if feature in ("mean", "sd", "min", "max"):
        return f"{short} ({unit})"
    if feature == "slope":
        return f"{short} ({unit}/s)"
    if feature == "peaks_per_min":
        return f"{short} (peaks/min)"
    if feature == "auc_per_min":
        return f"{short} ({unit}·s/min)"
    return short


def plot_title(signal, feature):
    short = SIGNAL_SHORT.get(signal, signal)
    return f"{FEATURE_LABELS.get(feature, feature)} {short} by condition"
