# Analysis Preprocessing + Multi-Signal — UI Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the Analysis page UI for multi-signal selection, a normalization dropdown, and the new `auc_per_min` feature; the server-rendered plots now carry feature-aware unit y-axes automatically.

**Architecture:** The `signal`→`signals[]` contract change plus the new `normalize` field touch `lib/analysis.ts`, `components/analysis/ResultBlock.tsx`, and `pages/Analysis.tsx` together (they're coupled through `CompareReq`/`plotUrl`), so Task 1 changes all three at once and ends tsc-clean. Task 2 rebuilds the bundle and verifies end-to-end.

**Tech Stack:** React 18 + TypeScript, Vite, Tailwind v4. Typecheck `cd hri_monitor/ui && npx tsc --noEmit`; build `npm run build` (emits to `../ui_dist`).

**Prereq:** The backend plan (`2026-06-17-analysis-preproc-backend.md`) is merged — `/api/analysis/compare` accepts `{signals[], features[], unit, normalize}`, `/api/analysis/plot` accepts `&normalize=`, options returns `normalizations`. Branch: `analysis-preproc` (same branch as backend, or a fresh one if backend already merged).

**Spec:** `docs/superpowers/specs/2026-06-17-analysis-preprocessing-multisignal.md`.

**Note:** `App.tsx` already renders `<Analysis />` for the Analysis page — no mount change needed; only a rebuild.

---

### Task 1: Wire multi-signal + normalize through the UI

**Files:**
- Modify: `hri_monitor/ui/src/lib/analysis.ts`
- Modify: `hri_monitor/ui/src/components/analysis/ResultBlock.tsx`
- Modify: `hri_monitor/ui/src/pages/Analysis.tsx`

- [ ] **Step 1: Update `hri_monitor/ui/src/lib/analysis.ts`**

(a) Change `CompareReq` (signal→signals, add normalize):

```typescript
export type CompareReq = {
  experiment_id: number;
  condition_ids: number[];
  signals: string[];
  features: string[];
  unit: "participant" | "recording";
  normalize: "none" | "range" | "zscore";
};
```

(b) Add `normalize?` to `AnalysisResult` (after `unit?: string;`):

```typescript
  normalize?: string;
```

(c) Add `normalizations?` to `AnalysisOptions` (after `features: string[];`):

```typescript
  normalizations?: string[];
```

(d) Add `auc_per_min` to `FEATURE_LABELS`:

```typescript
export const FEATURE_LABELS: Record<string, string> = {
  mean: "Mean", sd: "SD", min: "Min", max: "Max", slope: "Slope",
  peaks_per_min: "Peaks/min", auc_per_min: "Cumulative AUC/min",
};
```

(e) Add a normalization label map right after `FEATURE_LABELS`:

```typescript
export const NORMALIZATION_LABELS: Record<string, string> = {
  none: "None (raw)", range: "Range 0–1", zscore: "Z-score",
};
```

(f) Replace `plotUrl` (now takes an explicit `signal` and a base carrying `normalize`):

```typescript
  // plot download URL (used as <a href> / <img src> so the browser renders/saves it)
  plotUrl: (
    base: { experiment_id: number; condition_ids: number[]; unit: string; normalize: string },
    signal: string, feature: string, format: "svg" | "pdf",
  ) => {
    const p = new URLSearchParams();
    p.set("experiment_id", String(base.experiment_id));
    base.condition_ids.forEach((c) => p.append("condition_ids", String(c)));
    p.set("signal", signal); p.set("feature", feature);
    p.set("unit", base.unit); p.set("format", format); p.set("normalize", base.normalize);
    return `/api/analysis/plot?${p.toString()}`;
  },
```

- [ ] **Step 2: Update `hri_monitor/ui/src/components/analysis/ResultBlock.tsx`**

Change `plotBase` (drop `signal`, add `normalize`):

```typescript
  const plotBase = { experiment_id: req.experiment_id, condition_ids: req.condition_ids, unit: req.unit, normalize: req.normalize };
```

Update the three `plotUrl` calls to pass the signal explicitly. The `<img>` src:

```typescript
          <img className="w-full rounded-lg bg-white" alt={`${featLabel} ${sigLabel} by condition`}
            src={analysisApi.plotUrl(plotBase, res.signal ?? "", res.feature, "svg")} />
```

The SVG and PDF download links:

```typescript
            <a className="chip-dl" href={analysisApi.plotUrl(plotBase, res.signal ?? "", res.feature, "svg")}>⬇ SVG</a>
            <a className="chip-dl" href={analysisApi.plotUrl(plotBase, res.signal ?? "", res.feature, "pdf")}>⬇ PDF</a>
```

- [ ] **Step 3: Replace `hri_monitor/ui/src/pages/Analysis.tsx`** with the full updated page (multi-select signals, normalization dropdown, `auc` available automatically via options.features):

```typescript
import { useState } from "react";
import { ResultBlock } from "../components/analysis/ResultBlock";
import {
  type AnalysisResult, type CompareReq, analysisApi, useAnalysisOptions,
  FEATURE_LABELS, SIGNAL_LABELS, NORMALIZATION_LABELS,
} from "../lib/analysis";
import { useExperiments } from "../lib/experiments";

export function Analysis() {
  const { experiments } = useExperiments();
  const [expId, setExpId] = useState<number | null>(null);
  const options = useAnalysisOptions(expId);

  const [signals, setSignals] = useState<string[]>([]);
  const [features, setFeatures] = useState<string[]>(["mean"]);
  const [condIds, setCondIds] = useState<number[]>([]);
  const [unit, setUnit] = useState<"participant" | "recording">("participant");
  const [normalize, setNormalize] = useState<"none" | "range" | "zscore">("none");
  const [results, setResults] = useState<AnalysisResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastReq, setLastReq] = useState<CompareReq | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toggle = <T,>(arr: T[], v: T) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  const onPickExp = (id: number) => {
    setExpId(id); setSignals([]); setCondIds([]); setResults(null); setError(null);
  };

  const canRun = expId != null && signals.length > 0 && features.length > 0 && condIds.length >= 2 && !busy;

  const run = async () => {
    if (expId == null) return;
    const req: CompareReq = { experiment_id: expId, condition_ids: condIds, signals, features, unit, normalize };
    setBusy(true); setLastReq(req); setError(null);
    try {
      const r = await analysisApi.compare(req);
      setResults(r.results);
    } catch {
      setResults(null);
      setError("Analysis request failed. Check that the server is running and try again.");
    } finally { setBusy(false); }
  };

  const lbl = { fontSize: 10, textTransform: "uppercase" as const, letterSpacing: "0.05em", color: "var(--text-muted)" };
  const chipStyle = (on: boolean) =>
    on
      ? { background: "color-mix(in srgb, var(--accent) 18%, transparent)", color: "var(--accent)", border: "1px solid var(--accent)" }
      : { color: "var(--text-muted)", border: "1px solid color-mix(in srgb, var(--text-muted) 30%, transparent)" };

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>Analysis</h2>

      <div className="glass space-y-3 p-4">
        <div className="grid gap-3 md:grid-cols-3">
          <div>
            <div style={lbl} className="mb-1">Experiment</div>
            <select className="an-sel" value={expId ?? ""}
              onChange={(e) => onPickExp(Number(e.target.value))}>
              <option value="" disabled>Select…</option>
              {experiments.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
          </div>
          <div>
            <div style={lbl} className="mb-1">Unit of analysis</div>
            <div className="flex gap-2">
              {(["participant", "recording"] as const).map((u) => (
                <button key={u} onClick={() => setUnit(u)}
                  className="rounded-full px-3 py-1 text-[11px] font-semibold" style={chipStyle(unit === u)}>
                  {u === "participant" ? "Per participant" : "Per recording"}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div style={lbl} className="mb-1">Normalization</div>
            <select className="an-sel" value={normalize}
              onChange={(e) => setNormalize(e.target.value as "none" | "range" | "zscore")}>
              {(options?.normalizations ?? ["none", "range", "zscore"]).map((n) => (
                <option key={n} value={n}>{NORMALIZATION_LABELS[n] ?? n}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <div style={lbl} className="mb-1">Signals (pick ≥ 1)</div>
          <div className="flex flex-wrap gap-2">
            {options?.signals.map((s) => (
              <button key={s} onClick={() => setSignals((a) => toggle(a, s))}
                className="rounded-full px-3 py-1 text-[11px] font-semibold" style={chipStyle(signals.includes(s))}>
                {SIGNAL_LABELS[s] ?? s}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div style={lbl} className="mb-1">Features</div>
          <div className="flex flex-wrap gap-2">
            {options?.features.map((f) => (
              <button key={f} onClick={() => setFeatures((a) => toggle(a, f))}
                className="rounded-full px-3 py-1 text-[11px] font-semibold" style={chipStyle(features.includes(f))}>
                {FEATURE_LABELS[f] ?? f}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div style={lbl} className="mb-1">Conditions to compare (pick ≥ 2)</div>
          <div className="flex flex-wrap gap-2">
            {options?.conditions.map((c) => (
              <button key={c.id} onClick={() => setCondIds((a) => toggle(a, c.id))}
                className="rounded-full px-3 py-1 text-[11px] font-semibold" style={chipStyle(condIds.includes(c.id))}>
                {c.name}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center">
          <button onClick={run} disabled={!canRun}
            className="ml-auto rounded-lg px-5 py-2 text-sm font-bold"
            style={{ background: canRun ? "var(--accent)" : "color-mix(in srgb, var(--accent) 40%, transparent)",
                     color: "var(--base)", cursor: canRun ? "pointer" : "not-allowed" }}>
            {busy ? "Running…" : "▸ Run analysis"}
          </button>
        </div>
      </div>

      {error && (
        <div className="glass p-4 text-sm" style={{ color: "var(--err)" }}>{error}</div>
      )}
      {results && lastReq && results.length === 0 && (
        <div className="glass p-4 text-sm" style={{ color: "var(--text-muted)" }}>No results.</div>
      )}
      {results && lastReq && results.map((res, i) => (
        <ResultBlock key={`${res.signal}-${res.feature}-${i}`} res={res} req={lastReq} />
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Typecheck**

Run: `cd hri_monitor/ui && npx tsc --noEmit`
Expected: exit 0. (All three files now agree on the `CompareReq` shape and the new `plotUrl` signature.)

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/ui/src/lib/analysis.ts hri_monitor/ui/src/components/analysis/ResultBlock.tsx hri_monitor/ui/src/pages/Analysis.tsx
git commit -m "feat(analysis-ui): multi-select signals + normalization dropdown + auc feature"
```

---

### Task 2: Rebuild bundle + end-to-end verification

**Files:**
- Modify (generated): `hri_monitor/ui_dist/`

- [ ] **Step 1: Build**

Run: `cd hri_monitor/ui && npx tsc --noEmit && npm run build`
Expected: tsc exit 0, Vite emits fresh `index-*.js`/`index-*.css` to `../ui_dist` and updates `index.html`.

- [ ] **Step 2: Commit the bundle**

```bash
git add hri_monitor/ui_dist
git commit -m "build(analysis-ui): rebuild bundle for multi-signal + normalization"
```

- [ ] **Step 3: Live E2E against real data**

```bash
cd hri_monitor && .venv/bin/python run.py --no-browser > /tmp/an_ui_e2e.log 2>&1 &
for i in $(seq 1 20); do curl -sf http://127.0.0.1:8000/api/experiments >/dev/null 2>&1 && break; sleep 0.5; done
echo "--- bundle served ---"; curl -s http://127.0.0.1:8000/ | grep -oE 'index-[A-Za-z0-9_-]+\.(js|css)'
echo "--- options (expect normalizations + auc_per_min) ---"
curl -s http://127.0.0.1:8000/api/experiments/1/analysis/options | python3 -c "import sys,json;d=json.load(sys.stdin);print('norms',d.get('normalizations'),'| auc?', 'auc_per_min' in d['features'])"
echo "--- multi-signal compare (GSR+HR × mean+auc, range-normalized) ---"
curl -s -X POST http://127.0.0.1:8000/api/analysis/compare -H 'Content-Type: application/json' \
 -d '{"experiment_id":1,"condition_ids":[1,2],"signals":["shimmer.gsr","ppg.hr"],"features":["mean","auc_per_min"],"unit":"participant","normalize":"range"}' \
 | python3 -c "import sys,json;rs=json.load(sys.stdin)['results'];print('blocks:',len(rs));[print(' ',r['signal'],r['feature'],r.get('normalize'),'ok='+str(r.get('ok'))) for r in rs]"
echo "--- plot svg, range-normalized (y-axis should read 'GSR (normalized 0-1)') ---"
curl -s "http://127.0.0.1:8000/api/analysis/plot?experiment_id=1&condition_ids=1&condition_ids=2&signal=shimmer.gsr&feature=mean&unit=participant&format=svg&normalize=range" -o /tmp/an_norm.svg -w "  HTTP %{http_code} %{size_download}B\n"
grep -o 'normalized 0-1' /tmp/an_norm.svg | head -1
echo "--- plot svg, raw (y-axis should read 'GSR (µS)') ---"
curl -s "http://127.0.0.1:8000/api/analysis/plot?experiment_id=1&condition_ids=1&condition_ids=2&signal=shimmer.gsr&feature=mean&unit=participant&format=svg&normalize=none" -o /tmp/an_raw.svg -w "  HTTP %{http_code} %{size_download}B\n"
kill %1 2>/dev/null
```

Expected: bundle hash matches the new build; options lists `["none","range","zscore"]` + `auc_per_min`; compare returns 4 blocks (2 signals × 2 features) tagged `normalize=range`, all ok; both plots return HTTP 200 SVG; the normalized plot's y-axis text contains "normalized 0-1". Your recordings are untouched (read-only).

- [ ] **Step 4: Confirm clean + report**

```bash
cd /home/juanjose-ensta/Documents/HRIServcer && git status --short hri_monitor/   # only tracked source + ui_dist changes
```

Report: open the app → Analysis → pick multiple signals + features + a normalization → Run shows a block per signal×feature with unit-labeled plots. Milestone complete.
```
