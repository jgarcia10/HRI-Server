# Analysis Backend — Statistics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only `hub/analysis/` package: per-recording feature extraction, a condition-comparison engine (pingouin auto-selecting the right test with effect sizes + Holm post-hocs), matplotlib violin+box plot rendering (SVG/PDF), and a REST API — all hardware-free testable.

**Architecture:** `features.py` extracts per-recording features from the tidy CSV; `compare.py` gathers values per condition, aggregates to the unit of analysis, auto-detects pairing from participant overlap, and runs pingouin; `plots.py` renders the combined violin+box+points figure to SVG/PDF bytes via matplotlib's Agg backend; `router.py` exposes it. Reads the existing `hub/experiments` SQLite + CSVs; never mutates them.

**Tech Stack:** Python 3.10, numpy, **pingouin 0.6.1** (brings pandas/statsmodels/matplotlib), matplotlib (Agg), FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-06-16-hri-monitor-analysis.md`.

**Working dir:** `/home/juanjose-ensta/Documents/HRIServcer/hri_monitor`. Tests: `.venv/bin/python -m pytest`. `pytest.ini` sets pythonpath=. and disables ROS plugins — don't touch it.

**pingouin 0.6.1 output columns (verified — use these EXACT names):**
- `pg.ttest(x, y, paired=)` → `T, dof, p_val, cohen_d`
- `pg.wilcoxon(x, y)` → `W_val, p_val, RBC`   ·   `pg.mwu(x, y)` → `U_val, p_val, RBC`
- `pg.normality(df, dv=, group=)` → index=group, cols `W, pval, normal`
- `pg.rm_anova(data=, dv=, within=, subject=, detailed=True)` → row Source==within: `F, p_unc, ng2`
- `pg.friedman(data=, dv=, within=, subject=)` → `W, Q, p_unc`
- `pg.anova(data=, dv=, between=, detailed=True)` → row Source==between: `F, p_unc, np2`
- `pg.kruskal(data=, dv=, between=)` → `H, p_unc`
- `pg.pairwise_tests(data=, dv=, within=|between=, subject=, padjust='holm')` → `A, B, p_corr`

---

### Task 1: Dependency + feature extraction

**Files:**
- Modify: `hri_monitor/requirements.txt`
- Create: `hri_monitor/hub/analysis/__init__.py` (empty)
- Create: `hri_monitor/hub/analysis/features.py`
- Test: `hri_monitor/tests/test_an_features.py`

- [ ] **Step 1: Add the dependency + install it**

Append to `hri_monitor/requirements.txt`:

```
pingouin>=0.6
```

Run: `cd hri_monitor && .venv/bin/pip install -q pingouin && .venv/bin/python -c "import pingouin; print(pingouin.__version__)"`
Expected: prints a version ≥ 0.6 (pulls pandas/statsmodels/matplotlib). If install fails, report — the rest of this plan needs it.

- [ ] **Step 2: Create the package + write failing tests**

```bash
mkdir -p hri_monitor/hub/analysis && touch hri_monitor/hub/analysis/__init__.py
```

Create `hri_monitor/tests/test_an_features.py`:

```python
import math

from hub.analysis.features import FEATURES, extract_features


def write(tmp_path, rows):
    p = tmp_path / "rec.csv"
    p.write_text("t_offset,signal,value\n" + "".join(f"{t},{s},{v}\n" for t, s, v in rows))
    return p


def test_feature_list():
    assert FEATURES == ["mean", "sd", "min", "max", "slope", "peaks_per_min"]


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
```

- [ ] **Step 3: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_features.py -v`
Expected: FAIL — module missing.

- [ ] **Step 4: Implement `hri_monitor/hub/analysis/features.py`**

```python
"""Per-recording feature extraction from a tidy CSV (read-only). numpy-based."""
import csv

import numpy as np

FEATURES = ["mean", "sd", "min", "max", "slope", "peaks_per_min"]
_REFRACTORY_S = 0.3


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
    thr = float(np.mean(vs) + 0.5 * np.std(vs))
    peaks = []
    last_t = -1e9
    for i in range(1, len(vs) - 1):
        if vs[i] > vs[i - 1] and vs[i] >= vs[i + 1] and vs[i] > thr and ts[i] - last_t >= _REFRACTORY_S:
            peaks.append(ts[i]); last_t = ts[i]
    duration_min = (ts[-1] - ts[0]) / 60.0
    return float(len(peaks) / duration_min) if duration_min > 0 else 0.0


def extract_features(csv_path, signal) -> dict | None:
    """Return {mean,sd,min,max,slope,peaks_per_min} for `signal`, or None if absent."""
    ts, vs = _read_signal(csv_path, signal)
    if len(vs) == 0:
        return None
    return {
        "mean": float(np.mean(vs)),
        "sd": float(np.std(vs)),
        "min": float(np.min(vs)),
        "max": float(np.max(vs)),
        "slope": _slope(ts, vs),
        "peaks_per_min": _peaks_per_min(ts, vs),
    }
```

- [ ] **Step 5: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_features.py -v` → 5 passed. Full suite: `.venv/bin/python -m pytest tests -q` → all pass (95 + 5).

- [ ] **Step 6: Commit**

```bash
git add hri_monitor/requirements.txt hri_monitor/hub/analysis/__init__.py hri_monitor/hub/analysis/features.py hri_monitor/tests/test_an_features.py
git commit -m "feat(analysis): pingouin dep + per-recording feature extraction"
```

---

### Task 2: Gather + aggregate + pairing detection

**Files:**
- Create: `hri_monitor/hub/analysis/compare.py`
- Test: `hri_monitor/tests/test_an_gather.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_an_gather.py`:

```python
from hub.analysis.compare import gather

class FakeDB:
    """Minimal db stand-in: recordings keyed by (condition_id) -> [(participant_id, csv_path)]."""
    def __init__(self, rows):
        self._rows = rows  # list of dict(participant_id, condition_id, csv_path)
    def recordings_for_conditions(self, experiment_id, condition_ids):
        return [r for r in self._rows if r["condition_id"] in condition_ids]


def make_csv(tmp_path, name, signal, values):
    p = tmp_path / name
    p.write_text("t_offset,signal,value\n" + "".join(f"{i*0.1},{signal},{v}\n" for i, v in enumerate(values)))
    return str(p)


def test_per_participant_aggregation_and_paired(tmp_path):
    # P1 and P2 each have one recording in cond 1 and cond 2 → paired
    rows = [
        {"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "a", "shimmer.gsr", [2, 4])},
        {"participant_id": 2, "condition_id": 1, "csv_path": make_csv(tmp_path, "b", "shimmer.gsr", [3, 5])},
        {"participant_id": 1, "condition_id": 2, "csv_path": make_csv(tmp_path, "c", "shimmer.gsr", [5, 7])},
        {"participant_id": 2, "condition_id": 2, "csv_path": make_csv(tmp_path, "d", "shimmer.gsr", [6, 8])},
    ]
    g = gather(FakeDB(rows), experiment_id=1, condition_ids=[1, 2],
               signal="shimmer.gsr", feature="mean", unit="participant")
    assert g["paired"] is True
    # one value per (participant, condition); P1 cond1 mean of [2,4]=3
    assert {(r["subject"], r["condition_id"]): r["value"] for r in g["rows"]}[(1, 1)] == 3.0
    assert sorted(g["counts"].values()) == [2, 2]   # 2 subjects per condition


def test_unpaired_when_participants_differ(tmp_path):
    rows = [
        {"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "a", "shimmer.gsr", [2])},
        {"participant_id": 2, "condition_id": 2, "csv_path": make_csv(tmp_path, "b", "shimmer.gsr", [4])},
    ]
    g = gather(FakeDB(rows), 1, [1, 2], "shimmer.gsr", "mean", "participant")
    assert g["paired"] is False


def test_per_recording_unit_keeps_each_recording(tmp_path):
    rows = [
        {"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "a", "shimmer.gsr", [2])},
        {"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "b", "shimmer.gsr", [4])},
    ]
    g = gather(FakeDB(rows), 1, [1], "shimmer.gsr", "mean", "recording")
    assert g["counts"][1] == 2 and g["paired"] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_gather.py -v` → FAIL (module/function missing).

- [ ] **Step 3: Implement gather() in `hri_monitor/hub/analysis/compare.py`**

```python
"""Condition-comparison engine: gather feature values per condition, aggregate to
the unit of analysis, auto-detect pairing, and run the auto-selected pingouin test."""
from collections import defaultdict

from .features import extract_features


def gather(db, experiment_id, condition_ids, signal, feature, unit):
    """Return {rows: [{subject, condition_id, value}], paired: bool, counts: {cond: n}}.

    rows are one value per unit of analysis. `subject` is the participant id
    (per-participant: aggregated; per-recording: still the participant, but each
    recording is its own row). Pairing = per-participant AND identical participant
    set across all conditions (complete cases only)."""
    recs = db.recordings_for_conditions(experiment_id, condition_ids)
    # condition -> participant -> [feature values across that participant's recordings]
    per = defaultdict(lambda: defaultdict(list))
    recording_rows = []  # for the per-recording unit
    for r in recs:
        f = extract_features(r["csv_path"], signal)
        if f is None or feature not in f:
            continue
        v = f[feature]
        per[r["condition_id"]][r["participant_id"]].append(v)
        recording_rows.append({"subject": r["participant_id"], "condition_id": r["condition_id"], "value": v})

    if unit == "recording":
        counts = defaultdict(int)
        for row in recording_rows:
            counts[row["condition_id"]] += 1
        return {"rows": recording_rows, "paired": False, "counts": dict(counts)}

    # per-participant: average within (participant, condition)
    rows = []
    sets = []
    for cid in condition_ids:
        subjects = per.get(cid, {})
        sets.append(set(subjects))
        for pid, vals in subjects.items():
            rows.append({"subject": pid, "condition_id": cid, "value": sum(vals) / len(vals)})
    paired = len(sets) >= 2 and all(s == sets[0] and len(s) > 0 for s in sets)
    if paired:
        common = set.intersection(*sets)
        rows = [r for r in rows if r["subject"] in common]
    counts = defaultdict(int)
    for r in rows:
        counts[r["condition_id"]] += 1
    return {"rows": rows, "paired": paired, "counts": dict(counts)}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_gather.py -v` → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/analysis/compare.py hri_monitor/tests/test_an_gather.py
git commit -m "feat(analysis): gather + aggregate + pairing detection"
```

---

### Task 3: Test selection + result (pingouin)

**Files:**
- Modify: `hri_monitor/hub/analysis/compare.py`
- Modify: `hri_monitor/hub/experiments/db.py` (add `recordings_for_conditions`)
- Test: `hri_monitor/tests/test_an_compare.py`

- [ ] **Step 1: Add the db helper**

In `hri_monitor/hub/experiments/db.py`, add this method to the `Database` class (next to `list_recordings`):

```python
    def recordings_for_conditions(self, experiment_id, condition_ids):
        """All recordings of the given conditions in the experiment, with participant."""
        if not condition_ids:
            return []
        qs = ",".join("?" * len(condition_ids))
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                f"SELECT r.id, r.condition_id, r.csv_path, s.participant_id "
                f"FROM recording r JOIN session s ON r.session_id = s.id "
                f"WHERE s.experiment_id=? AND r.condition_id IN ({qs})",
                (experiment_id, *condition_ids))]
```

- [ ] **Step 2: Write the failing tests**

Create `hri_monitor/tests/test_an_compare.py`:

```python
import pytest

from hub.analysis.compare import run_test


def rows(pairs):
    # pairs: list of (subject, condition_id, value)
    return [{"subject": s, "condition_id": c, "value": v} for s, c, v in pairs]


def test_paired_two_conditions_significant():
    g = {"paired": True, "counts": {1: 5, 2: 5},
         "rows": rows([(i, 1, v) for i, v in enumerate([2, 3, 4, 3, 2])]
                      + [(i, 2, v) for i, v in enumerate([4, 5, 6, 5, 4])])}
    res = run_test(g, [1, 2], cond_names={1: "A", 2: "B"})
    assert res["ok"] is True
    assert res["test"] in ("paired t-test", "Wilcoxon signed-rank")
    assert res["design"] == "paired"
    assert res["p"] < 0.05
    assert res["effect_size"]["name"] and res["effect_size"]["magnitude"] in ("small", "medium", "large")
    assert "A" in res["interpretation"]


def test_unpaired_two_conditions():
    g = {"paired": False, "counts": {1: 5, 2: 5},
         "rows": rows([(i, 1, v) for i, v in enumerate([2, 3, 4, 3, 2])]
                      + [(10 + i, 2, v) for i, v in enumerate([5, 6, 7, 6, 5])])}
    res = run_test(g, [1, 2], cond_names={1: "A", 2: "B"})
    assert res["design"] == "unpaired"
    assert res["test"] in ("independent t-test", "Mann-Whitney U")


def test_three_conditions_paired_has_posthoc():
    base = [4.0, 4.2, 3.8, 4.1, 3.9, 4.0]
    g = {"paired": True, "counts": {1: 6, 2: 6, 3: 6},
         "rows": rows([(i, 1, v) for i, v in enumerate(base)]
                      + [(i, 2, v + 1.0) for i, v in enumerate(base)]
                      + [(i, 3, v + 2.0) for i, v in enumerate(base)])}
    res = run_test(g, [1, 2, 3], cond_names={1: "A", 2: "B", 3: "C"})
    assert res["test"] in ("repeated-measures ANOVA", "Friedman")
    assert res["ok"] and res["p"] < 0.05
    assert len(res["posthoc"]) == 3  # A-B, A-C, B-C


def test_insufficient_data_guard():
    g = {"paired": True, "counts": {1: 2, 2: 5}, "rows": rows([(0, 1, 1), (1, 1, 2)])}
    res = run_test(g, [1, 2], cond_names={1: "A", 2: "B"})
    assert res["ok"] is False and "insufficient" in res["reason"].lower()
```

- [ ] **Step 3: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_compare.py -v` → FAIL (run_test missing).

- [ ] **Step 4: Implement run_test() + compare() in `compare.py`**

Append to `hri_monitor/hub/analysis/compare.py`:

```python
import pandas as pd
import pingouin as pg

_MIN_PER_CONDITION = 3


def _magnitude(name, value):
    a = abs(value)
    if name == "cohen_d":
        return "large" if a >= 0.8 else "medium" if a >= 0.5 else "small"
    if name == "rank-biserial":
        return "large" if a >= 0.5 else "medium" if a >= 0.3 else "small"
    if name in ("partial eta^2", "generalized eta^2"):
        return "large" if a >= 0.14 else "medium" if a >= 0.06 else "small"
    if name == "Kendall W":
        return "large" if a >= 0.5 else "medium" if a >= 0.3 else "small"
    return "small"


def _descriptives(df, cond_names, normal_tbl):
    out = []
    for cid, sub in df.groupby("condition"):
        sp = float(normal_tbl.loc[cid, "pval"]) if cid in normal_tbl.index else None
        out.append({"condition": cond_names.get(cid, str(cid)), "n": int(len(sub)),
                    "mean": float(sub["value"].mean()), "sd": float(sub["value"].std(ddof=0)),
                    "shapiro_p": sp})
    return out


def run_test(g, condition_ids, cond_names):
    rows = g["rows"]
    counts = g["counts"]
    if any(counts.get(cid, 0) < _MIN_PER_CONDITION for cid in condition_ids):
        return {"ok": False, "reason": "insufficient data (need >=3 per condition)",
                "descriptives": [{"condition": cond_names.get(cid, str(cid)), "n": counts.get(cid, 0)}
                                 for cid in condition_ids]}
    df = pd.DataFrame(rows).rename(columns={"condition_id": "condition"})
    paired = g["paired"]
    k = len(condition_ids)
    normal_tbl = pg.normality(df, dv="value", group="condition")
    normal = bool(normal_tbl["normal"].all())
    posthoc = []

    if k == 2:
        a = df[df.condition == condition_ids[0]]["value"]
        b = df[df.condition == condition_ids[1]]["value"]
        if paired:
            if normal:
                r = pg.ttest(a.values, b.values, paired=True); test = "paired t-test"
                stat, p = float(r["T"].iloc[0]), float(r["p_val"].iloc[0])
                eff = {"name": "cohen_d", "value": float(r["cohen_d"].iloc[0])}
            else:
                r = pg.wilcoxon(a.values, b.values); test = "Wilcoxon signed-rank"
                stat, p = float(r["W_val"].iloc[0]), float(r["p_val"].iloc[0])
                eff = {"name": "rank-biserial", "value": float(r["RBC"].iloc[0])}
        else:
            if normal:
                r = pg.ttest(a.values, b.values, paired=False); test = "independent t-test"
                stat, p = float(r["T"].iloc[0]), float(r["p_val"].iloc[0])
                eff = {"name": "cohen_d", "value": float(r["cohen_d"].iloc[0])}
            else:
                r = pg.mwu(a.values, b.values); test = "Mann-Whitney U"
                stat, p = float(r["U_val"].iloc[0]), float(r["p_val"].iloc[0])
                eff = {"name": "rank-biserial", "value": float(r["RBC"].iloc[0])}
    else:
        if paired:
            if normal:
                r = pg.rm_anova(data=df, dv="value", within="condition", subject="subject", detailed=True)
                row = r[r["Source"] == "condition"].iloc[0]
                test = "repeated-measures ANOVA"; stat, p = float(row["F"]), float(row["p_unc"])
                eff = {"name": "generalized eta^2", "value": float(row["ng2"])}
            else:
                r = pg.friedman(data=df, dv="value", within="condition", subject="subject")
                test = "Friedman"; stat, p = float(r["Q"].iloc[0]), float(r["p_unc"].iloc[0])
                eff = {"name": "Kendall W", "value": float(r["W"].iloc[0])}
        else:
            if normal:
                r = pg.anova(data=df, dv="value", between="condition", detailed=True)
                row = r[r["Source"] == "condition"].iloc[0]
                test = "one-way ANOVA"; stat, p = float(row["F"]), float(row["p_unc"])
                eff = {"name": "partial eta^2", "value": float(row["np2"])}
            else:
                r = pg.kruskal(data=df, dv="value", between="condition")
                test = "Kruskal-Wallis"; stat, p = float(r["H"].iloc[0]), float(r["p_unc"].iloc[0])
                eff = {"name": "rank-biserial", "value": 0.0}
        if p < 0.05:
            kw = {"within": "condition", "subject": "subject"} if paired else {"between": "condition"}
            pt = pg.pairwise_tests(data=df, dv="value", padjust="holm", **kw)
            for _, prow in pt.iterrows():
                ac, bc = prow["A"], prow["B"]
                posthoc.append({"a": cond_names.get(ac, str(ac)), "b": cond_names.get(bc, str(bc)),
                                "p_corr": float(prow["p_corr"]), "sig": bool(prow["p_corr"] < 0.05)})

    eff["magnitude"] = _magnitude(eff["name"], eff["value"])
    descr = _descriptives(df, cond_names, normal_tbl)
    sig = p < 0.05
    posthoc_txt = ""
    if posthoc:
        pairs = [f"{x['a']} vs {x['b']} (p={x['p_corr']:.3f})" for x in posthoc if x["sig"]]
        posthoc_txt = " Post-hoc: " + (", ".join(pairs) if pairs else "no pair survived correction") + "."
    interp = (f"{test} ({'data normal' if normal else 'non-normal'}; {g['paired'] and 'within-subjects' or 'between-subjects'}; "
              f"{k} conditions): statistic={stat:.3f}, p={p:.4f}, {eff['name']}={eff['value']:.3f} ({eff['magnitude']}). "
              f"{'Significant.' if sig else 'Not significant.'}{posthoc_txt}")
    return {"ok": True, "test": test, "design": "paired" if g["paired"] else "unpaired",
            "normal": normal, "statistic": stat, "p": p, "effect_size": eff,
            "descriptives": descr, "posthoc": posthoc,
            "values": [{"condition": cond_names.get(r["condition_id"] if "condition_id" in r else r["condition"], ""),
                        "subject": r["subject"], "value": r["value"]} for r in rows],
            "interpretation": interp}


def compare(db, experiment_id, condition_ids, signal, feature, unit, cond_names):
    g = gather(db, experiment_id, condition_ids, signal, feature, unit)
    res = run_test(g, condition_ids, cond_names)
    res["signal"] = signal
    res["feature"] = feature
    res["unit"] = unit
    return res
```

- [ ] **Step 5: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_compare.py -v` → 4 passed. Full suite green.

Note: the `values` list builds from `gather`'s rows, which use key `condition_id`. The list-comprehension handles both keys defensively. If a test flags a KeyError on `condition`, ensure the rows passed to `run_test` use `condition_id` (they do from `gather`).

- [ ] **Step 6: Commit**

```bash
git add hri_monitor/hub/analysis/compare.py hri_monitor/hub/experiments/db.py hri_monitor/tests/test_an_compare.py
git commit -m "feat(analysis): pingouin test selection + effect sizes + posthoc"
```

---

### Task 4: Plots (matplotlib violin + box + points)

**Files:**
- Create: `hri_monitor/hub/analysis/plots.py`
- Test: `hri_monitor/tests/test_an_plots.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_an_plots.py`:

```python
from hub.analysis.plots import figure_bytes


def sample():
    return [{"condition": "A", "subject": 1, "value": 2.0},
            {"condition": "A", "subject": 2, "value": 3.0},
            {"condition": "A", "subject": 3, "value": 2.5},
            {"condition": "B", "subject": 1, "value": 4.0},
            {"condition": "B", "subject": 2, "value": 5.0},
            {"condition": "B", "subject": 3, "value": 4.5}]


def test_svg_bytes():
    b = figure_bytes(sample(), ["A", "B"], "Mean GSR by condition", "GSR (µS)", "svg")
    assert b[:5] == b"<?xml" or b"<svg" in b[:200]


def test_pdf_bytes():
    b = figure_bytes(sample(), ["A", "B"], "Mean GSR by condition", "GSR (µS)", "pdf")
    assert b[:4] == b"%PDF"


def test_empty_values_still_renders():
    b = figure_bytes([], ["A", "B"], "t", "y", "svg")
    assert len(b) > 0
```

- [ ] **Step 2: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_plots.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement `hri_monitor/hub/analysis/plots.py`**

```python
"""Render a combined violin + box + points figure to SVG/PDF bytes (headless)."""
import io

import matplotlib
matplotlib.use("Agg")  # no display; must precede pyplot import
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def figure_bytes(values, condition_order, title, ylabel, fmt) -> bytes:
    """values: [{condition, subject, value}]. Returns SVG or PDF bytes."""
    groups = [[v["value"] for v in values if v["condition"] == c] for c in condition_order]
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    positions = list(range(1, len(condition_order) + 1))
    nonempty = [(p, g) for p, g in zip(positions, groups) if len(g) > 0]
    if nonempty:
        vp_pos = [p for p, g in nonempty]
        vp_data = [g for p, g in nonempty]
        parts = ax.violinplot(vp_data, positions=vp_pos, showextrema=False)
        for body in parts["bodies"]:
            body.set_facecolor("#38bdf8"); body.set_alpha(0.25)
        ax.boxplot(vp_data, positions=vp_pos, widths=0.18, showfliers=False,
                   patch_artist=True,
                   boxprops=dict(facecolor="white", edgecolor="#0284c7"),
                   medianprops=dict(color="#0284c7"))
        rng = np.random.RandomState(0)
        for p, g in nonempty:
            jitter = (rng.rand(len(g)) - 0.5) * 0.12
            ax.scatter(np.full(len(g), p) + jitter, g, s=18, color="#0c4a6e", alpha=0.7, zorder=3)
    ax.set_xticks(positions)
    ax.set_xticklabels(condition_order, rotation=0)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt)
    plt.close(fig)
    return buf.getvalue()
```

- [ ] **Step 4: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_plots.py -v` → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/analysis/plots.py hri_monitor/tests/test_an_plots.py
git commit -m "feat(analysis): matplotlib violin+box+points svg/pdf rendering"
```

---

### Task 5: REST API router + wiring

**Files:**
- Create: `hri_monitor/hub/analysis/router.py`
- Modify: `hri_monitor/hub/server.py`
- Modify: `hri_monitor/run.py`
- Test: `hri_monitor/tests/test_an_api.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_an_api.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hub.analysis.router import build_analysis_router
from hub.experiments.db import Database


def setup(tmp_path):
    db = Database(tmp_path / "hri.db")
    exp = db.create_experiment("S", "")
    db.set_conditions(exp, ["A", "B"])
    conds = [c["id"] for c in db.get_experiment(exp)["conditions"]]
    app = FastAPI(); app.include_router(build_analysis_router(db))
    return db, exp, conds, TestClient(app)


def _rec(db, tmp_path, exp, pid_code, cid, signal, values, idx):
    pid = db.create_participant(exp, pid_code) if isinstance(pid_code, str) else pid_code
    sess = db.create_session(exp, pid)
    p = tmp_path / f"r{idx}.csv"
    p.write_text("t_offset,signal,value\n" + "".join(f"{i*0.1},{signal},{v}\n" for i, v in enumerate(values)))
    db.create_recording(sess, cid, str(p))
    return pid


def test_options_lists_present_signals(tmp_path):
    db, exp, conds, client = setup(tmp_path)
    _rec(db, tmp_path, exp, "P1", conds[0], "shimmer.gsr", [2, 3, 4], 1)
    opt = client.get(f"/api/experiments/{exp}/analysis/options").json()
    assert "shimmer.gsr" in opt["signals"]
    assert "mean" in opt["features"]
    assert any(c["name"] == "A" for c in opt["conditions"])


def test_compare_returns_one_result_per_feature(tmp_path):
    db, exp, conds, client = setup(tmp_path)
    for code, base in [("P1", 0), ("P2", 1), ("P3", 2)]:
        pid = _rec(db, tmp_path, exp, code, conds[0], "shimmer.gsr", [2 + base, 3 + base, 4 + base], f"{code}a")
        _rec(db, tmp_path, exp, pid, conds[1], "shimmer.gsr", [5 + base, 6 + base, 7 + base], f"{code}b")
    r = client.post("/api/analysis/compare", json={
        "experiment_id": exp, "condition_ids": conds, "signal": "shimmer.gsr",
        "features": ["mean", "sd"], "unit": "participant"})
    body = r.json()
    assert len(body["results"]) == 2
    assert {res["feature"] for res in body["results"]} == {"mean", "sd"}
    assert body["results"][0]["design"] == "paired"


def test_plot_endpoint_svg(tmp_path):
    db, exp, conds, client = setup(tmp_path)
    for code, base in [("P1", 0), ("P2", 1), ("P3", 2)]:
        pid = _rec(db, tmp_path, exp, code, conds[0], "shimmer.gsr", [2 + base, 3 + base], f"{code}a")
        _rec(db, tmp_path, exp, pid, conds[1], "shimmer.gsr", [5 + base, 6 + base], f"{code}b")
    r = client.get(f"/api/analysis/plot", params={
        "experiment_id": exp, "condition_ids": conds, "signal": "shimmer.gsr",
        "feature": "mean", "unit": "participant", "format": "svg"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_api.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement `hri_monitor/hub/analysis/router.py`**

```python
"""Analysis REST: options, compare (per-feature), plot (svg/pdf), values export."""
import csv
import io

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from .compare import compare
from .features import FEATURES
from .plots import figure_bytes

_ALL_SIGNALS = ["shimmer.gsr", "shimmer.ppg", "ppg.hr", "ppg.hrv", "rgb.blink",
                "thermal.forehead", "thermal.left_cheek", "thermal.right_cheek", "thermal.nose"]


def _present_signals(db, experiment_id):
    seen = set()
    for r in db.recordings_for_conditions(
            experiment_id, [c["id"] for c in (db.get_experiment(experiment_id) or {"conditions": []})["conditions"]]):
        try:
            with open(r["csv_path"]) as f:
                next(f, None)
                for line in f:
                    parts = line.split(",")
                    if len(parts) >= 2:
                        seen.add(parts[1])
                    if len(seen) >= len(_ALL_SIGNALS):
                        break
        except OSError:
            continue
    return [s for s in _ALL_SIGNALS if s in seen]


def _cond_names(db, experiment_id):
    exp = db.get_experiment(experiment_id)
    return {c["id"]: c["name"] for c in exp["conditions"]} if exp else {}


class CompareIn(BaseModel):
    experiment_id: int
    condition_ids: list[int]
    signal: str
    features: list[str]
    unit: str = "participant"


def build_analysis_router(db) -> APIRouter:
    r = APIRouter()

    @r.get("/api/experiments/{exp_id}/analysis/options")
    def options(exp_id: int):
        exp = db.get_experiment(exp_id)
        if not exp:
            return JSONResponse({"error": "not found"}, status_code=404)
        return {"signals": _present_signals(db, exp_id), "features": FEATURES,
                "conditions": [{"id": c["id"], "name": c["name"]} for c in exp["conditions"]]}

    @r.post("/api/analysis/compare")
    def do_compare(body: CompareIn):
        names = _cond_names(db, body.experiment_id)
        results = []
        for feat in body.features:
            try:
                results.append(compare(db, body.experiment_id, body.condition_ids,
                                       body.signal, feat, body.unit, names))
            except Exception as e:  # noqa: BLE001
                results.append({"ok": False, "feature": feat, "signal": body.signal,
                                "reason": f"could not compute: {e}"})
        return {"results": results}

    @r.get("/api/analysis/plot")
    def plot(experiment_id: int, signal: str, feature: str, format: str = "svg",
             unit: str = "participant", condition_ids: list[int] = Query(default=[])):
        names = _cond_names(db, experiment_id)
        res = compare(db, experiment_id, condition_ids, signal, feature, unit, names)
        order = [names.get(cid, str(cid)) for cid in condition_ids]
        title = f"{feature} of {signal} by condition"
        data = figure_bytes(res.get("values", []), order, title, f"{signal} · {feature}", format)
        media = "image/svg+xml" if format == "svg" else "application/pdf"
        return Response(data, media_type=media,
                        headers={"Content-Disposition": f'attachment; filename="analysis_{signal}_{feature}.{format}"'})

    @r.post("/api/analysis/export.csv")
    def export_values(body: CompareIn):
        names = _cond_names(db, body.experiment_id)
        buf = io.StringIO(); w = csv.writer(buf)
        w.writerow(["signal", "feature", "condition", "subject", "value"])
        for feat in body.features:
            res = compare(db, body.experiment_id, body.condition_ids, body.signal, feat, body.unit, names)
            for v in res.get("values", []):
                w.writerow([body.signal, feat, v["condition"], v["subject"], v["value"]])
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="analysis_values.csv"'})

    return r
```

- [ ] **Step 4: Wire into `server.py` and `run.py`**

In `hri_monitor/hub/server.py`, inside the `if experiments is not None:` block (right after the experiments router include), add the analysis router (it only needs the db):

```python
    if experiments is not None:
        from .experiments.router import build_router
        app.include_router(build_router(experiments["db"], experiments["controller"]))
        app.state.recording_controller = experiments["controller"]
        from .analysis.router import build_analysis_router
        app.include_router(build_analysis_router(experiments["db"]))
```

`run.py` already builds `experiments = {"db": exp_db, "controller": rec_ctrl}` and passes it — no change needed there (the analysis router reuses `exp_db`). Confirm by reading `run.py`.

- [ ] **Step 5: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_an_api.py -v` → 3 passed. Full suite: `.venv/bin/python -m pytest tests -q` → all green. Confirm existing server tests still pass (the analysis router is only added when `experiments` is provided).

- [ ] **Step 6: Commit**

```bash
git add hri_monitor/hub/analysis/router.py hri_monitor/hub/server.py hri_monitor/run.py hri_monitor/tests/test_an_api.py
git commit -m "feat(analysis): rest api (options/compare/plot/export) wired in"
```

---

### Task 6: Backend regression + real-data smoke

**Files:** none (verification).

- [ ] **Step 1: Full suite**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests -q`
Expected: all pass. Report the count (95 baseline + features 5 + gather 3 + compare 4 + plots 3 + api 3 = 113).

- [ ] **Step 2: Real-data smoke (your recorded sessions)**

If `data/recordings/` has CSVs and `data/hri.db` has ≥2 conditions with ≥3 participants, run a live compare:

```bash
cd hri_monitor && .venv/bin/python run.py --no-browser & sleep 4
EXP=1   # adjust to a real experiment id
echo "--- options ---"; curl -s "http://127.0.0.1:8000/api/experiments/$EXP/analysis/options"
echo; echo "--- compare mean GSR across conditions 1,2 ---"
curl -s -X POST http://127.0.0.1:8000/api/analysis/compare -H 'Content-Type: application/json' \
  -d "{\"experiment_id\":$EXP,\"condition_ids\":[1,2],\"signal\":\"shimmer.gsr\",\"features\":[\"mean\"],\"unit\":\"participant\"}" \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['results'][0];print('ok',r.get('ok'),'test',r.get('test'),'p',r.get('p'),'interp:',r.get('interpretation','')[:160])"
echo "--- plot svg bytes ---"; curl -s "http://127.0.0.1:8000/api/analysis/plot?experiment_id=$EXP&condition_ids=1&condition_ids=2&signal=shimmer.gsr&feature=mean&unit=participant&format=svg" | head -c 40
kill %1; git checkout config.yaml 2>/dev/null || true
```

Expected: options lists your present signals; compare returns a test + p + interpretation (or "insufficient data" if you have <3 participants per condition — report which); the plot returns SVG bytes. This is read-only — your recordings are untouched.

- [ ] **Step 3: Confirm clean + report**

```bash
git status --short   # clean (data/ gitignored)
```

Report backend complete; the UI plan (`2026-06-16-analysis-ui.md`) is next.
