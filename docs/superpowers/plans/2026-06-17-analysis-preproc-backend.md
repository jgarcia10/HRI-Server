# Analysis Preprocessing + Multi-Signal — Backend Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `hub/analysis/` with per-user normalization (None/Range/Z-score), a new `auc_per_min` feature, multi-signal compare, and feature-aware plot units.

**Architecture:** A new `normalize.py` computes per-participant scaling params from all of a participant's recordings (every condition) and yields transforms applied before feature extraction; `features.py` gains `auc_per_min` + an optional `transform`; `units.py` maps signal/feature/normalize → y-axis label + title; `compare.py` threads a `normalize` arg; `router.py` takes `signals[]` + `normalize`. Raw single-signal path stays byte-for-byte identical.

**Tech Stack:** Python 3.10, numpy 2.2 (`np.trapezoid`), pingouin, FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-06-17-analysis-preprocessing-multisignal.md`.

**Working dir:** `/home/juanjose-ensta/Documents/HRIServcer/hri_monitor`. Tests: `.venv/bin/python -m pytest`. Never touch `pytest.ini` or `data/`. Branch: `analysis-preproc`.

---

### Task 1: `auc_per_min` feature + optional transform

**Files:**
- Modify: `hri_monitor/hub/analysis/features.py`
- Test: `hri_monitor/tests/test_an_features.py` (append)

- [ ] **Step 1: Write failing tests** — append to `hri_monitor/tests/test_an_features.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_features.py -k "auc or transform or list_includes" -v`
Expected: FAIL (auc_per_min missing / transform kwarg unexpected).

- [ ] **Step 3: Implement in `hri_monitor/hub/analysis/features.py`**

Add the trapezoid alias near the top (after `import numpy as np`):

```python
_trapz = getattr(np, "trapezoid", np.trapz)  # numpy>=2 renamed trapz → trapezoid
```

Update `FEATURES`:

```python
FEATURES = ["mean", "sd", "min", "max", "slope", "peaks_per_min", "auc_per_min"]
```

Add the AUC helper (next to `_peaks_per_min`):

```python
def _auc_per_min(ts, vs):
    if len(vs) < 2 or len(ts) < 2:
        return 0.0
    duration_min = (ts[-1] - ts[0]) / 60.0
    if duration_min == 0:
        return 0.0
    return float(_trapz(vs, ts) / duration_min)
```

Change `extract_features` to accept a transform and compute AUC:

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_features.py -v` → all pass (existing + 4 new). Full suite: `.venv/bin/python -m pytest tests -q` → all green.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/analysis/features.py hri_monitor/tests/test_an_features.py
git commit -m "feat(analysis): auc_per_min feature + optional pre-extraction transform"
```

---

### Task 2: Normalization module + db helper

**Files:**
- Create: `hri_monitor/hub/analysis/normalize.py`
- Modify: `hri_monitor/hub/experiments/db.py` (add `recordings_for_experiment`)
- Test: `hri_monitor/tests/test_an_normalize.py`

- [ ] **Step 1: Add the db helper.** In `hri_monitor/hub/experiments/db.py`, add to the `Database` class next to `recordings_for_conditions` (read the surrounding code to match indentation):

```python
    def recordings_for_experiment(self, experiment_id):
        """All recordings of the experiment (every condition), with participant."""
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT r.id, r.condition_id, r.csv_path, s.participant_id "
                "FROM recording r JOIN session s ON r.session_id = s.id "
                "WHERE s.experiment_id=?", (experiment_id,))]
```

- [ ] **Step 2: Write failing tests** — create `hri_monitor/tests/test_an_normalize.py`:

```python
import numpy as np

from hub.analysis.normalize import params, participant_transforms


class FakeDB:
    def __init__(self, rows):
        self._rows = rows  # [{participant_id, condition_id, csv_path}]
    def recordings_for_experiment(self, experiment_id):
        return list(self._rows)


def make_csv(tmp_path, name, signal, values):
    p = tmp_path / name
    p.write_text("t_offset,signal,value\n" + "".join(f"{i*0.1},{signal},{v}\n" for i, v in enumerate(values)))
    return str(p)


def test_params_range():
    a, b = params([2.0, 4.0, 6.0], "range")
    assert a == 2.0 and b == 4.0  # min=2, max-min=4


def test_params_zscore():
    a, b = params([2.0, 4.0, 6.0], "zscore")
    assert a == 4.0 and abs(b - np.std([2, 4, 6])) < 1e-9


def test_params_constant_signal_has_unit_divisor():
    a, b = params([3.0, 3.0, 3.0], "range")
    assert b == 1.0  # max-min == 0 → guarded to 1.0
    az, bz = params([3.0, 3.0, 3.0], "zscore")
    assert bz == 1.0


def test_participant_transforms_use_all_conditions(tmp_path):
    # P1 has values 0..10 spread across TWO conditions → range params from BOTH
    rows = [
        {"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "a", "shimmer.gsr", [0.0, 10.0])},
        {"participant_id": 1, "condition_id": 2, "csv_path": make_csv(tmp_path, "b", "shimmer.gsr", [5.0])},
    ]
    tf = participant_transforms(FakeDB(rows), 1, "shimmer.gsr", "range")
    assert set(tf) == {1}
    # range over P1's full data is [0,10] → 10 maps to 1.0, 0 maps to 0.0, 5 maps to 0.5
    out = tf[1](np.array([0.0, 5.0, 10.0]))
    assert np.allclose(out, [0.0, 0.5, 1.0])


def test_participant_transforms_none_method_empty(tmp_path):
    rows = [{"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "a", "shimmer.gsr", [1.0])}]
    assert participant_transforms(FakeDB(rows), 1, "shimmer.gsr", "none") == {}
```

- [ ] **Step 3: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_normalize.py -v` → FAIL (module missing).

- [ ] **Step 4: Implement `hri_monitor/hub/analysis/normalize.py`**

```python
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
```

- [ ] **Step 5: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_normalize.py -v` → 5 passed. Full suite green.

- [ ] **Step 6: Commit**

```bash
git add hri_monitor/hub/analysis/normalize.py hri_monitor/hub/experiments/db.py hri_monitor/tests/test_an_normalize.py
git commit -m "feat(analysis): per-user normalization params + recordings_for_experiment"
```

---

### Task 3: Units / labels module

**Files:**
- Create: `hri_monitor/hub/analysis/units.py`
- Test: `hri_monitor/tests/test_an_units.py`

- [ ] **Step 1: Write failing tests** — create `hri_monitor/tests/test_an_units.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_units.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement `hri_monitor/hub/analysis/units.py`**

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_units.py -v` → 3 passed. Full suite green.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/analysis/units.py hri_monitor/tests/test_an_units.py
git commit -m "feat(analysis): feature-aware unit + title labels for plots"
```

---

### Task 4: Thread `normalize` through compare/gather

**Files:**
- Modify: `hri_monitor/hub/analysis/compare.py`
- Test: `hri_monitor/tests/test_an_compare.py` (append) and `hri_monitor/tests/test_an_gather.py` (append)

- [ ] **Step 1: Write failing tests** — append to `hri_monitor/tests/test_an_gather.py`:

```python
def test_gather_normalize_preserves_condition_order(tmp_path):
    # P1 & P2 each: cond1 lower than cond2. Range-normalize per participant across
    # both conditions → absolute values change but A<B per participant is preserved.
    from hub.analysis.normalize import participant_transforms  # noqa: F401 (ensures import path)

    class FullFakeDB(FakeDB):
        def recordings_for_experiment(self, experiment_id):
            return list(self._rows)

    rows = [
        {"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "a", "shimmer.gsr", [0.0, 2.0])},
        {"participant_id": 2, "condition_id": 1, "csv_path": make_csv(tmp_path, "b", "shimmer.gsr", [10.0, 12.0])},
        {"participant_id": 1, "condition_id": 2, "csv_path": make_csv(tmp_path, "c", "shimmer.gsr", [8.0, 10.0])},
        {"participant_id": 2, "condition_id": 2, "csv_path": make_csv(tmp_path, "d", "shimmer.gsr", [18.0, 20.0])},
    ]
    g = gather(FullFakeDB(rows), 1, [1, 2], "shimmer.gsr", "mean", "participant", normalize="range")
    by = {(r["subject"], r["condition_id"]): r["value"] for r in g["rows"]}
    assert by[(1, 1)] < by[(1, 2)] and by[(2, 1)] < by[(2, 2)]   # order preserved
    # P1 global range is [0,10]; cond1 mean=1 → 0.1, cond2 mean=9 → 0.9
    assert abs(by[(1, 1)] - 0.1) < 1e-9 and abs(by[(1, 2)] - 0.9) < 1e-9
```

Append to `hri_monitor/tests/test_an_compare.py`:

```python
def test_compare_adds_normalize_tag(tmp_path):
    # uses the gather path via a small in-memory db-like object
    class DB:
        def __init__(self, rows): self._rows = rows
        def recordings_for_conditions(self, e, cids): return [r for r in self._rows if r["condition_id"] in cids]
        def recordings_for_experiment(self, e): return list(self._rows)
    import pathlib
    from hub.analysis.compare import compare
    def mk(name, vals):
        p = tmp_path / name
        p.write_text("t_offset,signal,value\n" + "".join(f"{i*0.1},shimmer.gsr,{v}\n" for i, v in enumerate(vals)))
        return str(p)
    rows = []
    for pid in (1, 2, 3):
        rows.append({"participant_id": pid, "condition_id": 1, "csv_path": mk(f"{pid}a", [1.0 + pid, 2.0 + pid, 3.0 + pid])})
        rows.append({"participant_id": pid, "condition_id": 2, "csv_path": mk(f"{pid}b", [4.0 + pid, 5.0 + pid, 6.0 + pid])})
    res = compare(DB(rows), 1, [1, 2], "shimmer.gsr", "mean", "participant", {1: "A", 2: "B"}, normalize="zscore")
    assert res["normalize"] == "zscore"
    assert res["ok"] is True and res["signal"] == "shimmer.gsr"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_gather.py::test_gather_normalize_preserves_condition_order tests/test_an_compare.py::test_compare_adds_normalize_tag -v`
Expected: FAIL (`gather()`/`compare()` take no `normalize`).

- [ ] **Step 3: Implement in `hri_monitor/hub/analysis/compare.py`**

Add the import at the top (next to `from .features import extract_features`):

```python
from .normalize import participant_transforms
```

Change `gather`'s signature and the extract call:

```python
def gather(db, experiment_id, condition_ids, signal, feature, unit, normalize="none"):
```

Right after `recs = db.recordings_for_conditions(experiment_id, condition_ids)`, add:

```python
    transforms = participant_transforms(db, experiment_id, signal, normalize) if normalize != "none" else {}
```

Change the extract line inside the loop from `f = extract_features(r["csv_path"], signal)` to:

```python
            f = extract_features(r["csv_path"], signal, transform=transforms.get(r["participant_id"]))
```

Change `compare`:

```python
def compare(db, experiment_id, condition_ids, signal, feature, unit, cond_names, normalize="none"):
    g = gather(db, experiment_id, condition_ids, signal, feature, unit, normalize)
    res = run_test(g, condition_ids, cond_names)
    res["signal"] = signal
    res["feature"] = feature
    res["unit"] = unit
    res["normalize"] = normalize
    return res
```

- [ ] **Step 4: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_gather.py tests/test_an_compare.py -v` → all pass. Full suite green (the raw path is unchanged: `normalize="none"` builds no transforms and `transforms.get(pid)` returns None → identical to before).

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/analysis/compare.py hri_monitor/tests/test_an_gather.py hri_monitor/tests/test_an_compare.py
git commit -m "feat(analysis): thread per-user normalize through gather/compare"
```

---

### Task 5: REST API — multi-signal + normalize + plot units

**Files:**
- Modify: `hri_monitor/hub/analysis/router.py`
- Test: `hri_monitor/tests/test_an_api.py` (append)

- [ ] **Step 1: Write failing tests** — append to `hri_monitor/tests/test_an_api.py`:

```python
def test_compare_multi_signal_and_feature(tmp_path):
    db, exp, conds, client = setup(tmp_path)
    for code, base in [("P1", 0), ("P2", 1), ("P3", 2)]:
        for cidx, cid in enumerate(conds):
            pid = (db.create_participant(exp, code) if cidx == 0 else pid)  # noqa: F821
            sess = db.create_session(exp, pid)
            p = tmp_path / f"{code}_{cid}.csv"
            p.write_text("t_offset,signal,value\n" + "".join(
                f"{i*0.1},shimmer.gsr,{2+base+cidx*3+i}\n{i*0.1},ppg.hr,{60+base+cidx*2+i}\n" for i in range(3)))
            db.create_recording(sess, cid, str(p))
    r = client.post("/api/analysis/compare", json={
        "experiment_id": exp, "condition_ids": conds, "signals": ["shimmer.gsr", "ppg.hr"],
        "features": ["mean", "auc_per_min"], "unit": "participant", "normalize": "range"})
    results = r.json()["results"]
    assert len(results) == 4  # 2 signals × 2 features
    tags = {(x["signal"], x["feature"]) for x in results}
    assert tags == {("shimmer.gsr", "mean"), ("shimmer.gsr", "auc_per_min"),
                    ("ppg.hr", "mean"), ("ppg.hr", "auc_per_min")}
    assert all(x.get("normalize") == "range" for x in results)


def test_options_lists_normalizations(tmp_path):
    db, exp, conds, client = setup(tmp_path)
    opt = client.get(f"/api/experiments/{exp}/analysis/options").json()
    assert opt["normalizations"] == ["none", "range", "zscore"]
    assert "auc_per_min" in opt["features"]


def test_plot_with_normalize_param(tmp_path):
    db, exp, conds, client = setup(tmp_path)
    for code, base in [("P1", 0), ("P2", 1), ("P3", 2)]:
        pid = db.create_participant(exp, code)
        for cid in conds:
            sess = db.create_session(exp, pid)
            p = tmp_path / f"{code}_{cid}.csv"
            p.write_text("t_offset,signal,value\n" + "".join(f"{i*0.1},shimmer.gsr,{2+base+cid+i}\n" for i in range(3)))
            db.create_recording(sess, cid, str(p))
    r = client.get("/api/analysis/plot", params={
        "experiment_id": exp, "condition_ids": conds, "signal": "shimmer.gsr",
        "feature": "mean", "unit": "participant", "format": "svg", "normalize": "range"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg")
```

NOTE: the existing `setup`/`_rec` helpers at the top of `test_an_api.py` send the OLD single-`signal` body. The first new test builds its own recordings inline. Keep the existing tests working by ALSO updating them in Step 3 (they post `signal`, which becomes `signals`).

- [ ] **Step 2: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_api.py -v`
Expected: the new tests FAIL, and the existing `test_compare_*`/`test_plot_*` tests may fail once the model changes — that's expected; fix in Step 3.

- [ ] **Step 3: Implement in `hri_monitor/hub/analysis/router.py`**

Add the import:

```python
from .units import plot_title, y_axis_label
```

Replace `CompareIn`:

```python
class CompareIn(BaseModel):
    experiment_id: int
    condition_ids: list[int]
    signals: list[str]
    features: list[str]
    unit: str = "participant"
    normalize: str = "none"
```

Replace `do_compare`:

```python
    @r.post("/api/analysis/compare")
    def do_compare(body: CompareIn):
        names = _cond_names(db, body.experiment_id)
        results = []
        for sig in body.signals:
            for feat in body.features:
                try:
                    results.append(compare(db, body.experiment_id, body.condition_ids,
                                           sig, feat, body.unit, names, normalize=body.normalize))
                except Exception as e:  # noqa: BLE001
                    results.append({"ok": False, "signal": sig, "feature": feat,
                                    "unit": body.unit, "normalize": body.normalize,
                                    "values": [], "reason": f"could not compute: {e}"})
        return JSONResponse(_json_safe({"results": results}))
```

Replace `plot` (add `normalize`, use units):

```python
    @r.get("/api/analysis/plot")
    def plot(experiment_id: int, signal: str, feature: str, format: str = "svg",
             unit: str = "participant", normalize: str = "none",
             condition_ids: list[int] = Query(default=[])):
        if format not in ("svg", "pdf"):
            return JSONResponse({"error": "format must be svg or pdf"}, status_code=400)
        names = _cond_names(db, experiment_id)
        res = compare(db, experiment_id, condition_ids, signal, feature, unit, names, normalize=normalize)
        order = [names.get(cid, str(cid)) for cid in condition_ids]
        data = figure_bytes(res.get("values", []), order, plot_title(signal, feature),
                            y_axis_label(signal, feature, normalize), format)
        media = "image/svg+xml" if format == "svg" else "application/pdf"
        return Response(data, media_type=media,
                        headers={"Content-Disposition": f'attachment; filename="analysis_{signal}_{feature}.{format}"'})
```

Replace `export_values` (multi-signal):

```python
    @r.post("/api/analysis/export.csv")
    def export_values(body: CompareIn):
        names = _cond_names(db, body.experiment_id)
        buf = io.StringIO(); w = csv.writer(buf)
        w.writerow(["signal", "feature", "condition", "subject", "value"])
        for sig in body.signals:
            for feat in body.features:
                res = compare(db, body.experiment_id, body.condition_ids, sig, feat, body.unit, names,
                              normalize=body.normalize)
                for v in res.get("values", []):
                    w.writerow([sig, feat, v["condition"], v["subject"], v["value"]])
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="analysis_values.csv"'})
```

Add `normalizations` to `options` (in the returned dict):

```python
        return {"signals": _present_signals(db, exp_id), "features": FEATURES,
                "normalizations": ["none", "range", "zscore"],
                "conditions": [{"id": c["id"], "name": c["name"]} for c in exp["conditions"]]}
```

Update the EXISTING tests in `hri_monitor/tests/test_an_api.py` that POST the old body: change `"signal": "shimmer.gsr"` to `"signals": ["shimmer.gsr"]` in `test_compare_returns_one_result_per_feature` and `test_export_csv_has_rows` (the plot tests use a query param `signal=` which is unchanged). After editing, the per-feature test asserts `len(results) == 2` still holds (1 signal × 2 features).

- [ ] **Step 4: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_api.py -v` → all pass. Full suite: `.venv/bin/python -m pytest tests -q` → all green.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/analysis/router.py hri_monitor/tests/test_an_api.py
git commit -m "feat(analysis): multi-signal compare + normalize param + unit-labeled plots"
```

---

### Task 6: Regression + real-data smoke

**Files:** none (verification).

- [ ] **Step 1: Full suite**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests -q` → all pass. Report the count.

- [ ] **Step 2: Real-data smoke (read-only, in-process)**

```bash
cd hri_monitor && .venv/bin/python - <<'PY'
from hub.experiments.db import Database
from hub.analysis.compare import compare
from hub.analysis.units import y_axis_label, plot_title
db = Database("data/hri.db")
names = {c["id"]: c["name"] for c in db.get_experiment(1)["conditions"]}
cids = list(names)
for norm in ("none", "range", "zscore"):
    r = compare(db, 1, cids, "shimmer.gsr", "auc_per_min", "participant", names, normalize=norm)
    print(f"GSR auc_per_min [{norm}]: ok={r.get('ok')} test={r.get('test')} p={r.get('p')} "
          f"ylabel={y_axis_label('shimmer.gsr','auc_per_min',norm)!r}")
print("title:", plot_title("shimmer.gsr", "mean"))
PY
```

Expected: all three normalizations return a result on your real "Touch Screen" data; raw ylabel `'GSR (µS·s/min)'`, range `'GSR (normalized 0-1)'`, zscore `'GSR (z-score)'`. Your recordings are untouched (read-only).

- [ ] **Step 3: Confirm clean**

```bash
cd /home/juanjose-ensta/Documents/HRIServcer && git status --short hri_monitor/   # only tracked source changes; data/ untouched
```

Report backend complete; the UI plan (`2026-06-17-analysis-preproc-ui.md`) is next.
