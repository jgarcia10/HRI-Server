# HRI Monitor — Analysis Page (Statistics)

**Date:** 2026-06-16
**Status:** Approved pending user review
**Scope:** A new Analysis page + backend that compares experimental **conditions** across participants using the recorded data, with automatic statistical test selection, effect sizes, combined violin+box plots, and publication-ready SVG/PDF export. Read-only over the existing experiments data (SQLite metadata + tidy CSVs). Builds on the bus/experiments/Clinical Frost architecture.

## 1. Goal

Let a researcher answer "does this signal/feature differ between conditions?" without leaving the platform:
1. Pick an experiment → a signal → **one or more features** → the conditions to compare → unit of analysis.
2. For each chosen feature, extract a per-recording value, aggregate per the unit, run the correct statistical test, and report the result with an effect size and a plain-language verdict.
3. Show a combined **violin + box plot** (with participant points) per condition, rendered by matplotlib.
4. **Export** the figure (SVG + PDF), the per-unit values (CSV), and the results (JSON).

Available signals: `shimmer.gsr`, `shimmer.ppg`, `ppg.hr`, `ppg.hrv`, `rgb.blink`, `thermal.forehead`, `thermal.left_cheek`, `thermal.right_cheek`, `thermal.nose`. Features: **mean, SD, min, max, slope, peaks/min**.

## 2. Decisions (from brainstorming)

- **Unit of analysis:** toggle per comparison — **per-participant** (default; average a participant's recordings within a condition to one value → no pseudo-replication) or **per-recording** (each recording a point).
- **Pairing:** **auto-detected** from participant overlap. If every compared condition shares the same participant set (per-participant unit) → paired/within-subjects (complete cases); otherwise unpaired. Per-recording → unpaired. The chosen design is reported.
- **Stats engine:** **pingouin** (added dependency; brings pandas, statsmodels, matplotlib). Used for normality, all tests, post-hocs, and effect sizes.
- **Features per run:** **multi-select** — one result block per selected feature.
- **Plots:** combined **violin + box + participant points**, rendered server-side with **matplotlib** (headless Agg/SVG backend). The page embeds the SVG; exports are the same figure in **SVG and PDF**.
- **Scope:** comparisons within ONE experiment.

## 3. Architecture

New `hub/analysis/` package (read-only over `hub/experiments` data):

```
hub/analysis/
├── __init__.py
├── features.py      # per-recording feature extraction from a tidy CSV
├── compare.py       # gather → aggregate → detect pairing → run pingouin → result
├── plots.py         # matplotlib violin+box+points → SVG/PDF bytes
└── router.py        # REST: options, compare, plot, exports
ui/src/
├── pages/Analysis.tsx
├── lib/analysis.ts                 # API client + types
└── components/analysis/*           # ControlBar, ResultBlock, etc.
```

`requirements.txt` gains `pingouin`. `hub/experiments/stats.py` stays; `features.py` is the richer extractor.

## 4. Feature extraction (`features.py`)

`extract_features(csv_path, signal) -> dict | None` reads only the rows for `signal` from the tidy CSV as ordered `(t_offset, value)` pairs and returns:
- `mean`, `sd` (population), `min`, `max`
- `slope` — least-squares linear fit of value vs `t_offset` (units/second); 0.0 if <2 points
- `peaks_per_min` — count of local maxima (a point greater than its neighbours and above `mean + 0.5*sd`, with a refractory of ≥0.3 s between peaks) divided by recording duration in minutes; 0.0 if duration is 0
Returns `None` if the signal has no samples in the file. numpy-based; pure; unit-tested.

`FEATURES = ["mean", "sd", "min", "max", "slope", "peaks_per_min"]` (display labels in the UI).

## 5. Comparison engine (`compare.py`)

`compare(db, experiment_id, condition_ids, signal, feature, unit) -> dict`:

1. **Gather:** for each condition, walk sessions → recordings (via db), `extract_features` for `signal`, take `feature`. Per-recording rows carry `(participant_id, condition_id, value)`.
2. **Aggregate:** if `unit == "participant"`, average a participant's values within a condition → one row per (participant, condition). If `unit == "recording"`, keep each recording row (participant_id still attached).
3. **Pairing:** `paired = (unit == "participant")` AND every condition shares the identical participant set; restrict to complete-case participants (present in all conditions). Else unpaired.
4. **Insufficient data guard:** any condition with <3 observations → return `{"ok": False, "reason": "insufficient data (need ≥3 per condition)", "descriptives": [...]}`.
5. **Normality:** Shapiro-Wilk per condition (`pg.normality`); `normal = all groups p > 0.05`.
6. **Test selection** (build a long DataFrame `subject, condition, value`):

   | k conditions | paired | normal | test (pingouin) |
   |---|---|---|---|
   | 2 | yes | yes/no | `pg.ttest(paired=True)` / `pg.wilcoxon` |
   | 2 | no | yes/no | `pg.ttest` / `pg.mwu` |
   | 3+ | yes | yes/no | `pg.rm_anova` / `pg.friedman` |
   | 3+ | no | yes/no | `pg.anova` / `pg.kruskal` |

7. **Post-hoc (3+ and omnibus p<0.05):** `pg.pairwise_tests(..., padjust='holm', within/between per design)`.
8. **Effect size:** from pingouin's output — Cohen's d (t-tests), rank-biserial (Wilcoxon/MWU), partial η² (ANOVA), Kendall's W (Friedman) — each with a small/medium/large label.
9. **Return** a dict: `ok`, `test` (name), `design` ("paired"/"unpaired"), `normal`, `statistic`, `p`, `effect_size {name, value, magnitude}`, `descriptives` [{condition, n, mean, sd, shapiro_p}], `posthoc` [{a, b, p_corr, sig}], `values` [{condition, subject, value}] (for the plot), and `interpretation` (plain-language string naming the test, why it was chosen, the result, and significant post-hoc pairs).

## 6. Plots (`plots.py`)

`figure_bytes(values, condition_order, title, ylabel, fmt) -> bytes` with `matplotlib` (`matplotlib.use("Agg")`):
- One axis; for each condition: a **violin** (distribution), a narrower **box** overlaid (median/quartiles/whiskers), and the individual **points** jittered on top.
- Clinical-Frost-ish styling (clean, light), title + y-axis label (signal + feature), condition names on x.
- `fmt="svg"` → `image/svg+xml` bytes; `fmt="pdf"` → `application/pdf` bytes. Rendered to an in-memory buffer; never writes display.
- Tested for: returns non-empty bytes starting with the SVG/PDF magic for each format, given a small values list.

## 7. REST API (`hub/analysis/router.py`, mounted in `create_app`)

- `GET /api/experiments/{id}/analysis/options` → `{signals: [...present in data...], features: [...], conditions: [{id,name}]}`.
- `POST /api/analysis/compare` body `{experiment_id, condition_ids[], signal, features[], unit}` → `{results: [<compare() per feature>]}`.
- `GET /api/analysis/plot` query `experiment_id, condition_ids, signal, feature, unit, format=svg|pdf` → the matplotlib figure bytes with the right media type + `Content-Disposition` for downloads. (Recomputes values via `compare`.)
- `POST /api/analysis/export.csv` body same as compare → tidy per-unit values CSV (`condition, subject, signal, feature, value`).
Mounted via the existing `experiments=` wiring (or a parallel `analysis=` dict) so milestone-1/2 server tests are unaffected. New routes registered before the static mount.

## 8. UI (`ui/`, Clinical Frost)

`Analysis.tsx` replaces the sidebar "Analysis" placeholder.
- **Control bar:** experiment select, signal select, **multi-select feature chips**, **condition multi-select chips**, **unit toggle** (per-participant default / per-recording), **Run**.
- **Per-feature result block** (stacked, one per selected feature): verdict card (significant pill, test name + why, statistic/p/effect size, post-hoc summary), the embedded matplotlib **violin+box SVG** (fetched from `/api/analysis/plot?...format=svg`), the descriptives+normality table, and export buttons (**⬇ SVG**, **⬇ PDF** via the plot endpoint; **⬇ values CSV**; **⬇ results JSON** from the in-hand result).
- Insufficient-data blocks show the guard message instead of a test.
- `lib/analysis.ts`: typed client + `useAnalysisOptions(expId)`; `runCompare(...)`. Reuses tokens/StatusChip; rebuilt `ui_dist` committed.

## 9. Error handling

- <3 per condition → per-feature "insufficient data" block; other features still run.
- Signal not present in the data → not offered in options.
- pingouin/test exceptions (degenerate input, zero variance) → that feature's block shows "could not compute (reason)"; never crashes the request or hub.
- Plot endpoint failures return a clear error, not a broken image.
- Read-only throughout; figures render to memory buffers.

## 10. Testing (hardware-free, pytest)

- `features.py`: mean/SD/min/max/slope/peaks on known inputs (incl. a synthetic ramp for slope, a synthetic peaky signal for peaks/min); `None` for absent signal.
- `compare.py`: paired t-test, Wilcoxon, independent t-test, Mann-Whitney, RM-ANOVA, Friedman, one-way ANOVA, Kruskal — each on a small fixture with a known pingouin/scipy result; pairing auto-detection (same vs different participant sets); per-participant aggregation; insufficient-data guard; interpretation string shape.
- `plots.py`: SVG and PDF outputs are non-empty and start with the expected magic bytes.
- API: options/compare/plot/export via the FastAPI test client with a temp DB + injected CSVs; multi-feature returns one result per feature.
- Existing suite stays green. `pingouin` is added to requirements and installed in the dev venv for these tests (CI note: needs the dep).

## 11. Out of scope

- Comparisons across multiple experiments; mixed-design / covariate models; time-series/epoch analysis within a recording.
- CL/T model estimates as a signal (works automatically once that topic is recorded; not built here).
- Re-running stats live during recording.
