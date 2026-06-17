# HRI Monitor — Analysis Preprocessing + Multi-Signal

**Date:** 2026-06-17
**Status:** Approved (design confirmed in session)
**Scope:** Extend the merged Analysis page with (1) an optional per-user normalization preprocessing stage, (2) a new GSR cumulative feature (AUC/min), (3) multi-signal selection (signal × feature result blocks), and (4) feature-aware unit labels on plot y-axes. Builds on `hub/analysis/` and the Clinical Frost Analysis UI.

## 1. Decisions (confirmed)

- **Normalization reference:** **per participant, across ALL their recordings in the experiment** (every condition), per signal. Removes individual scale/baseline differences while preserving between-condition contrasts (so paired/RM tests still detect effects).
- **Normalization method:** selectable per analysis — **None** (raw, default) · **Range 0–1** (Lykken: `(x-min)/(max-min)`) · **Z-score** (`(x-mean)/sd`). Applied to the raw time-series *before* feature extraction.
- **New feature `auc_per_min`:** trapezoidal integral of the signal over time ÷ duration in minutes (µS·s/min for GSR). Added to the global feature list (computable for any signal; most meaningful for GSR).
- **Multi-signal:** the signal picker becomes multi-select; one run yields a result block per **signal × feature**.
- **Y-axis units:** feature-aware (see §6), replacing today's `"shimmer.gsr · mean"`.
- **Default behaviour unchanged:** with normalization None and a single signal, results are identical to today (raw).

## 2. Normalization (`hub/analysis/normalize.py`, new)

For each participant P and signal S, the normalization parameters are computed from **the concatenation of every value of S across all of P's recordings in the experiment** (all conditions), then the same transform is applied to each of P's recordings before feature extraction.

- `participant_values(db, experiment_id, signal) -> {participant_id: np.ndarray}` — reads every recording of the experiment (via a new `db.recordings_for_experiment`), groups S's values by participant. Skips unreadable CSVs (OSError).
- `params(values, method) -> (a, b)`:
  - `range` → `a = min`, `b = (max - min)`; if `b == 0` → `b = 1.0` (constant signal → all 0).
  - `zscore` → `a = mean`, `b = std(ddof=0)`; if `b == 0` → `b = 1.0`.
- `participant_transforms(db, experiment_id, signal, method) -> {participant_id: callable(np.ndarray)->np.ndarray}` where each callable is `lambda v: (v - a) / b`. Returns `{}` for an unknown method; participants with no S samples get no entry (and fall back to identity → raw).
- `method` is one of `"range"`, `"zscore"`. `"none"` means no transforms are built.

## 3. Feature extraction (`hub/analysis/features.py`)

- Add `"auc_per_min"` to `FEATURES` (now 7 features).
- `_auc_per_min(ts, vs)`: `np.trapz(vs, ts) / duration_min`; `0.0` if `<2` points or `duration_min == 0`.
- `extract_features(csv_path, signal, transform=None) -> dict | None`: if `transform` is given, apply it to the values array immediately after reading (`vs = transform(vs)`) and before computing any feature. All existing features plus `auc_per_min` are then computed on the (possibly normalized) values. `transform=None` preserves current raw behaviour exactly.

## 4. Comparison engine (`hub/analysis/compare.py`)

- `gather(db, experiment_id, condition_ids, signal, feature, unit, normalize="none")`:
  - If `normalize != "none"`: build `transforms = participant_transforms(db, experiment_id, signal, normalize)` once, and call `extract_features(csv_path, signal, transform=transforms.get(participant_id))` per recording (a participant without a transform → identity).
  - If `normalize == "none"`: unchanged (`extract_features(csv_path, signal)`).
  - Everything else (aggregation, pairing, counts) unchanged.
- `compare(db, experiment_id, condition_ids, signal, feature, unit, cond_names, normalize="none")`: threads `normalize` into `gather`, and adds `res["normalize"] = normalize` (plus existing `signal`/`feature`/`unit`).
- `run_test` is unchanged — it operates on the gathered values regardless of normalization.

## 5. Database (`hub/experiments/db.py`)

- Add `recordings_for_experiment(experiment_id)` → all recordings of the experiment (every condition) with `id, condition_id, csv_path, participant_id`, via the same `recording JOIN session` pattern as `recordings_for_conditions` but filtered only by `s.experiment_id`.

## 6. Units (`hub/analysis/units.py`, new)

- `SIGNAL_UNITS`: `shimmer.gsr→µS`, `shimmer.ppg→mV`, `ppg.hr→bpm`, `ppg.hrv→ms`, `rgb.blink→/min`, `thermal.*→°C`.
- `SIGNAL_SHORT`: `shimmer.gsr→GSR`, `shimmer.ppg→PPG`, `ppg.hr→HR`, `ppg.hrv→HRV`, `rgb.blink→Blink`, `thermal.forehead→Forehead`, `thermal.left_cheek→L cheek`, `thermal.right_cheek→R cheek`, `thermal.nose→Nose`.
- `FEATURE_LABELS`: `mean→Mean, sd→SD, min→Min, max→Max, slope→Slope, peaks_per_min→Peaks/min, auc_per_min→Cumulative AUC/min`.
- `y_axis_label(signal, feature, normalize) -> str`:
  - `normalize == "range"` → `f"{short} (normalized 0–1)"`
  - `normalize == "zscore"` → `f"{short} (z-score)"`
  - else (raw), feature-aware base unit:
    - `mean|sd|min|max` → `f"{short} ({unit})"`
    - `slope` → `f"{short} ({unit}/s)"`
    - `peaks_per_min` → `f"{short} (peaks/min)"`
    - `auc_per_min` → `f"{short} ({unit}·s/min)"`
  - Unknown signal → fall back to the raw signal id.
- `plot_title(signal, feature) -> str` → `f"{FEATURE_LABELS[feature]} {short} by condition"` (e.g. "Mean GSR by condition").

## 7. REST API (`hub/analysis/router.py`)

- `CompareIn`: replace `signal: str` with `signals: list[str]`; add `normalize: str = "none"`.
- `POST /api/analysis/compare`: nested loop over `signals × features`; each `compare(..., normalize=body.normalize)`; one result per pair (results carry `signal`, `feature`, `unit`, `normalize`). Error wrapper dict includes `signal`, `feature`, `unit`, `normalize`, `values: []`, `reason`. Still `_json_safe`-wrapped.
- `GET /api/analysis/plot`: add `normalize: str = "none"`; ylabel = `units.y_axis_label(signal, feature, normalize)`, title = `units.plot_title(signal, feature)`; pass `normalize` into `compare`. Format guard unchanged.
- `POST /api/analysis/export.csv`: loop `signals × features`; CSV columns `signal, feature, condition, subject, value` (already correct). Pass `normalize`.
- `GET options`: add `"normalizations": ["none", "range", "zscore"]` to the response (UI builds the dropdown from this). `features` continues to come from `FEATURES` (now includes `auc_per_min`).

## 8. UI (`hri_monitor/ui/`)

- `lib/analysis.ts`:
  - `CompareReq`: `signal: string` → `signals: string[]`; add `normalize: "none" | "range" | "zscore"`.
  - `AnalysisResult`: add optional `normalize?: string`.
  - `AnalysisOptions`: add `normalizations?: string[]`.
  - `plotUrl(base, signal, feature, format)` where `base = {experiment_id, condition_ids, unit, normalize}` — appends `normalize` and an explicit `signal`.
  - `FEATURE_LABELS`: add `auc_per_min: "Cumulative AUC/min"`.
  - `NORMALIZATION_LABELS = { none: "None (raw)", range: "Range 0–1", zscore: "Z-score" }`.
- `pages/Analysis.tsx`:
  - `signals: string[]` multi-select chips (mirrors the feature/condition chips); default `[]`.
  - `normalize` state + a `<select className="an-sel">` (None/Range/Z-score) in the control bar.
  - `canRun` also requires `signals.length > 0`.
  - Request sends `signals` + `normalize`; one `<ResultBlock>` per result.
  - On experiment change, reset signals too.
- `components/analysis/ResultBlock.tsx`:
  - `plotBase = {experiment_id, condition_ids, unit, normalize}` from `req`; call `analysisApi.plotUrl(plotBase, res.signal!, res.feature, fmt)`.
  - No other change (verdict already shows the signal label).
- Rebuild `ui_dist`, commit.

## 9. Error handling

- Normalization with degenerate per-user data (constant signal) → `b=1`, values become 0; the insufficient-data / NaN guards downstream still apply.
- A signal absent from a participant's recordings → no transform → identity (raw) for that participant; compare's existing skip logic handles absent signals.
- Multi-signal: a failing signal×feature pair degrades to its own `{ok:false}` block; others still render.

## 10. Testing (hardware-free, pytest)

- `normalize.py`: `params` for range and zscore on known arrays; constant-signal → b=1 → zeros; `participant_transforms` groups by participant across conditions and yields callables that map a known input to the expected normalized output.
- `features.py`: `auc_per_min` on a known ramp/constant (e.g. constant c over T seconds → `c*T / (T/60)` = `c*60`); `extract_features` with a transform applied (e.g. an affine transform shifts mean predictably); absent signal still `None`.
- `compare.py`: `gather(..., normalize="range")` preserves condition ordering within a participant (a synthetic 2-participant, 2-condition fixture where normalization changes absolute values but keeps A<B per participant); `compare` adds `normalize` to the result.
- `units.py`: `y_axis_label` for each feature × {none,range,zscore}; `plot_title`.
- `router.py`: compare with `signals=[a,b]`, `features=[mean,auc_per_min]`, `normalize=range` → 4 result blocks with the right signal/feature/normalize tags; plot endpoint with `normalize` returns valid bytes; options lists `normalizations`.
- Existing suite stays green (raw single-signal path unchanged).

## 11. Out of scope

- Filtering / artifact rejection / phasic-tonic (Ledalab-style) decomposition.
- Baseline-condition-relative normalization (considered, not chosen).
- Per-signal different normalization in one run (one normalization choice applies to all selected signals).
