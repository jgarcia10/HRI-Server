"""Per-user normalization: compute scaling params from ALL of a participant's
recordings of a signal (across every condition), apply before feature extraction.
Normalizing per-user (not per-condition) removes individual scale differences while
preserving the between-condition contrasts the statistics test."""
import csv
from collections import defaultdict

import numpy as np

from .clean import clean_values


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
            vals = clean_values(signal, _read_values(r["csv_path"], signal))
        except OSError:
            continue
        if len(vals):
            out[r["participant_id"]].extend(vals.tolist())
    return {pid: np.array(v, dtype=float) for pid, v in out.items()}


def params(values, method):
    """Return (a, b) so the transform is (x - a) / b. Constant signal → b = 1.0."""
    values = np.asarray(values, dtype=float)
    if method == "range":
        a = float(np.percentile(values, 1))
        b = float(np.percentile(values, 99)) - a
    elif method == "zscore":
        a = float(np.mean(values)); b = float(np.std(values))
    else:
        return (0.0, 1.0)
    return (a, b if b != 0 else 1.0)


def _make_transform(a, b, clip=None):
    if clip is None:
        return lambda v: (np.asarray(v, dtype=float) - a) / b
    lo, hi = clip
    return lambda v: np.clip((np.asarray(v, dtype=float) - a) / b, lo, hi)


def participant_transforms(db, experiment_id, signal, method):
    """{participant_id: callable(np.ndarray)->np.ndarray} or {} for method 'none'."""
    if method not in ("range", "zscore"):
        return {}
    clip = (0.0, 1.0) if method == "range" else None
    return {pid: _make_transform(*params(vals, method), clip=clip)
            for pid, vals in participant_values(db, experiment_id, signal).items()}
