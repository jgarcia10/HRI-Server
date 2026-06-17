"""Per-recording feature extraction from a tidy CSV (read-only). numpy-based."""
import csv

import numpy as np

_trapz = getattr(np, "trapezoid", np.trapz)  # numpy>=2 renamed trapz → trapezoid

FEATURES = ["mean", "sd", "min", "max", "slope", "peaks_per_min", "auc_per_min"]
_REFRACTORY_S = 0.3
_PEAK_K_SD = 0.5


def _read_signal(csv_path, signal):
    ts, vs = [], []
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 3 and row[1] == signal:
                try:
                    ts.append(float(row[0])); vs.append(float(row[2]))
                except ValueError:
                    continue
    return np.array(ts), np.array(vs)


def _slope(ts, vs):
    if len(ts) < 2 or np.ptp(ts) == 0:
        return 0.0
    # least-squares slope of vs ~ ts
    return float(np.polyfit(ts, vs, 1)[0])


def _peaks_per_min(ts, vs):
    if len(vs) < 3 or len(ts) < 2:
        return 0.0
    thr = float(np.mean(vs) + _PEAK_K_SD * np.std(vs))
    # strict-rising / non-strict-falling avoids double-counting flat tops
    count = 0
    last_t = -1e9
    for i in range(1, len(vs) - 1):
        if vs[i] > vs[i - 1] and vs[i] >= vs[i + 1] and vs[i] > thr and ts[i] - last_t >= _REFRACTORY_S:
            count += 1
            last_t = ts[i]
    duration_min = (ts[-1] - ts[0]) / 60.0
    return float(count / duration_min) if duration_min > 0 else 0.0


def _auc_per_min(ts, vs):
    if len(vs) < 2 or len(ts) < 2:
        return 0.0
    duration_min = (ts[-1] - ts[0]) / 60.0
    if duration_min == 0:
        return 0.0
    return float(_trapz(vs, ts) / duration_min)


def extract_features(csv_path, signal, transform=None) -> dict | None:
    """Return {mean,sd,min,max,slope,peaks_per_min,auc_per_min} for `signal`, or None
    if absent. If `transform` is given, it is applied to the values array before any
    feature is computed (used for per-user normalization)."""
    ts, vs = _read_signal(csv_path, signal)
    if len(vs) == 0:
        return None
    if transform is not None:
        vs = transform(vs)
    return {
        "mean": float(np.mean(vs)),
        "sd": float(np.std(vs)),
        "min": float(np.min(vs)),
        "max": float(np.max(vs)),
        "slope": _slope(ts, vs),
        "peaks_per_min": _peaks_per_min(ts, vs),
        "auc_per_min": _auc_per_min(ts, vs),
    }
