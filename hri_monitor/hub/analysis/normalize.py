"""Per-user normalization: compute scaling params from ALL of a participant's
recordings of a signal (across every condition), apply before feature extraction.
Normalizing per-user (not per-condition) removes individual scale differences while
preserving the between-condition contrasts the statistics test."""
import csv
from collections import defaultdict

import numpy as np


def _read_values(csv_path, signal):
    vs = []
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 3 and row[1] == signal:
                try:
                    vs.append(float(row[2]))
                except ValueError:
                    continue
    return vs


def participant_values(db, experiment_id, signal):
    """{participant_id: np.ndarray of every value of `signal` across all conditions}."""
    out = defaultdict(list)
    for r in db.recordings_for_experiment(experiment_id):
        try:
            vals = _read_values(r["csv_path"], signal)
        except OSError:
            continue
        if vals:
            out[r["participant_id"]].extend(vals)
    return {pid: np.array(v, dtype=float) for pid, v in out.items()}


def params(values, method):
    """Return (a, b) so the transform is (x - a) / b. Constant signal → b = 1.0."""
    values = np.asarray(values, dtype=float)
    if method == "range":
        a = float(np.min(values)); b = float(np.max(values) - a)
    elif method == "zscore":
        a = float(np.mean(values)); b = float(np.std(values))
    else:
        return (0.0, 1.0)
    return (a, b if b != 0 else 1.0)


def _make_transform(a, b):
    return lambda v: (np.asarray(v, dtype=float) - a) / b


def participant_transforms(db, experiment_id, signal, method):
    """{participant_id: callable(np.ndarray)->np.ndarray} or {} for method 'none'."""
    if method not in ("range", "zscore"):
        return {}
    return {pid: _make_transform(*params(vals, method))
            for pid, vals in participant_values(db, experiment_id, signal).items()}
