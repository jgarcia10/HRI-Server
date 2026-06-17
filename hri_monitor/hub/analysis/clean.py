"""Artifact rejection: drop non-finite and physically-impossible samples before
feature extraction and normalization. Bounds are per-signal physiological limits."""
import numpy as np

_THERMAL_LO, _THERMAL_HI = 10.0, 45.0  # plausible facial skin temperature (°C)


def _value_mask(signal, vs):
    """Boolean mask of samples to KEEP (finite + within physiological bounds)."""
    vs = np.asarray(vs, dtype=float)
    m = np.isfinite(vs)
    if signal == "shimmer.gsr":
        m &= vs >= 0                      # negative skin conductance is impossible
    elif signal == "ppg.hr":
        m &= vs > 0                       # heart rate must be positive
    elif signal.startswith("thermal."):
        m &= (vs >= _THERMAL_LO) & (vs <= _THERMAL_HI)
    return m


def clean(signal, ts, vs):
    """Filter (ts, vs) to finite timestamps and kept values; returns (ts, vs) arrays."""
    ts = np.asarray(ts, dtype=float)
    vs = np.asarray(vs, dtype=float)
    m = _value_mask(signal, vs) & np.isfinite(ts)
    return ts[m], vs[m]


def clean_values(signal, vs):
    """Filter a values array (no timestamps) to kept samples."""
    vs = np.asarray(vs, dtype=float)
    return vs[_value_mask(signal, vs)]
