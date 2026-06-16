# Analysis Page — UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Clinical Frost "Analysis" page that drives the analysis backend: pick experiment → signal → multi-select features → conditions → unit, Run, and render one result block per feature (verdict card + embedded matplotlib violin+box SVG + descriptives table + SVG/PDF/CSV/JSON export).

**Architecture:** A typed API client (`lib/analysis.ts`) wraps the backend; `pages/Analysis.tsx` holds the control bar + state; `components/analysis/ResultBlock.tsx` renders one feature's result. Mirrors the existing `lib/experiments.ts` + `pages/Experiments.tsx` patterns and the Clinical Frost token system (`var(--accent)`, `.glass`, `.tnum`). The page mounts in `App.tsx` replacing the "Analysis" placeholder. Built bundle (`ui_dist/`) is committed (it is git-tracked).

**Tech Stack:** React 18 + TypeScript, Vite, Tailwind v4, lucide-react. Dev: `cd hri_monitor/ui && npm run dev`; build: `npm run build` (emits to `../ui_dist`).

**Prereq:** The backend plan (`2026-06-16-analysis-backend.md`) is merged — endpoints `GET /api/experiments/{id}/analysis/options`, `POST /api/analysis/compare`, `GET /api/analysis/plot`, `POST /api/analysis/export.csv` exist and return the documented shapes.

**Backend result shape (per feature) the UI consumes:**
```
{ ok, test, design, normal, statistic, p,
  effect_size: {name, value, magnitude},
  descriptives: [{condition, n, mean, sd, shapiro_p}],
  posthoc: [{a, b, p_corr, sig}],
  values: [{condition, subject, value}],
  interpretation, signal, feature, unit }
// insufficient/error: { ok:false, reason, feature, signal, descriptives? }
```

---

### Task 1: API client (`lib/analysis.ts`)

**Files:**
- Create: `hri_monitor/ui/src/lib/analysis.ts`

- [ ] **Step 1: Implement the client + types**

Create `hri_monitor/ui/src/lib/analysis.ts`:

```typescript
import { useCallback, useEffect, useState } from "react";

export type EffectSize = { name: string; value: number; magnitude: string };
export type Descriptive = { condition: string; n: number; mean?: number; sd?: number; shapiro_p?: number | null };
export type PostHoc = { a: string; b: string; p_corr: number; sig: boolean };
export type ValueRow = { condition: string; subject: number; value: number };
export type AnalysisResult = {
  ok: boolean;
  feature: string;
  signal?: string;
  unit?: string;
  reason?: string;                 // when ok === false
  test?: string;
  design?: "paired" | "unpaired";
  normal?: boolean;
  statistic?: number;
  p?: number;
  effect_size?: EffectSize;
  descriptives?: Descriptive[];
  posthoc?: PostHoc[];
  values?: ValueRow[];
  interpretation?: string;
};
export type AnalysisOptions = {
  signals: string[];
  features: string[];
  conditions: { id: number; name: string }[];
};
export type CompareReq = {
  experiment_id: number;
  condition_ids: number[];
  signal: string;
  features: string[];
  unit: "participant" | "recording";
};

export const SIGNAL_LABELS: Record<string, string> = {
  "shimmer.gsr": "GSR (µS)", "shimmer.ppg": "PPG (mV)", "ppg.hr": "HR (bpm)",
  "ppg.hrv": "HRV (ms)", "rgb.blink": "Blink (/min)",
  "thermal.forehead": "Forehead (°C)", "thermal.left_cheek": "L cheek (°C)",
  "thermal.right_cheek": "R cheek (°C)", "thermal.nose": "Nose (°C)",
};
export const FEATURE_LABELS: Record<string, string> = {
  mean: "Mean", sd: "SD", min: "Min", max: "Max", slope: "Slope", peaks_per_min: "Peaks/min",
};

async function j<T>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(url, opts);
  return r.json();
}

export const analysisApi = {
  options: (expId: number) => j<AnalysisOptions>(`/api/experiments/${expId}/analysis/options`),
  compare: (req: CompareReq) =>
    j<{ results: AnalysisResult[] }>("/api/analysis/compare", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req),
    }),
  // download URLs (used as <a href> so the browser saves the file)
  plotUrl: (req: Omit<CompareReq, "features">, feature: string, format: "svg" | "pdf") => {
    const p = new URLSearchParams();
    p.set("experiment_id", String(req.experiment_id));
    req.condition_ids.forEach((c) => p.append("condition_ids", String(c)));
    p.set("signal", req.signal); p.set("feature", feature);
    p.set("unit", req.unit); p.set("format", format);
    return `/api/analysis/plot?${p.toString()}`;
  },
  valuesCsvUrl: "/api/analysis/export.csv",
};

export function useAnalysisOptions(expId: number | null) {
  const [options, setOptions] = useState<AnalysisOptions | null>(null);
  const refresh = useCallback(async () => {
    if (expId == null) { setOptions(null); return; }
    setOptions(await analysisApi.options(expId));
  }, [expId]);
  useEffect(() => { refresh(); }, [refresh]);
  return options;
}
```

- [ ] **Step 2: Typecheck**

Run: `cd hri_monitor/ui && npx tsc --noEmit`
Expected: no errors (an unused-symbol warning is fine until Task 2/3 consume them; if `noUnusedLocals` makes tsc fail, proceed — Task 2 imports them).

- [ ] **Step 3: Commit**

```bash
git add hri_monitor/ui/src/lib/analysis.ts
git commit -m "feat(analysis-ui): typed api client + options hook"
```

---

### Task 2: Result block component (`components/analysis/ResultBlock.tsx`)

**Files:**
- Create: `hri_monitor/ui/src/components/analysis/ResultBlock.tsx`

- [ ] **Step 1: Implement the component**

Create `hri_monitor/ui/src/components/analysis/ResultBlock.tsx`:

```typescript
import { type AnalysisResult, type CompareReq, analysisApi, FEATURE_LABELS, SIGNAL_LABELS } from "../../lib/analysis";

const fmt = (n: unknown, d = 2) =>
  typeof n === "number" && Number.isFinite(n) ? n.toFixed(d) : "—";

function downloadBlob(data: string, type: string, filename: string) {
  const blob = new Blob([data], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  a.click(); URL.revokeObjectURL(url);
}

function downloadJson(res: AnalysisResult) {
  downloadBlob(JSON.stringify(res, null, 2), "application/json",
    `analysis_${res.signal ?? "signal"}_${res.feature}.json`);
}

function downloadCsv(res: AnalysisResult) {
  const rows = ["condition,subject,signal,feature,value"];
  for (const v of res.values ?? []) rows.push(`${v.condition},${v.subject},${res.signal ?? ""},${res.feature},${v.value}`);
  downloadBlob(rows.join("\n"), "text/csv", `analysis_${res.signal ?? "signal"}_${res.feature}_values.csv`);
}

export function ResultBlock({ res, req }: { res: AnalysisResult; req: CompareReq }) {
  const featLabel = FEATURE_LABELS[res.feature] ?? res.feature;
  const sigLabel = SIGNAL_LABELS[res.signal ?? ""] ?? res.signal ?? "";

  if (!res.ok) {
    return (
      <div className="glass p-4">
        <div className="mb-1 text-sm font-semibold" style={{ color: "var(--text)" }}>{featLabel} · {sigLabel}</div>
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>{res.reason ?? "could not compute"}</div>
        {res.descriptives && (
          <div className="mt-2 text-[11px]" style={{ color: "var(--text-muted)" }}>
            {res.descriptives.map((d) => `${d.condition}: n=${d.n}`).join(" · ")}
          </div>
        )}
      </div>
    );
  }

  const sig = (res.p ?? 1) < 0.05;
  const plotBase = { experiment_id: req.experiment_id, condition_ids: req.condition_ids, signal: req.signal, unit: req.unit };

  return (
    <div className="glass p-4 space-y-3">
      {/* verdict */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full px-2 py-0.5 text-[10px] font-bold"
          style={sig
            ? { background: "color-mix(in srgb, var(--ok) 18%, transparent)", color: "var(--ok)" }
            : { background: "color-mix(in srgb, var(--text-muted) 15%, transparent)", color: "var(--text-muted)" }}>
          {sig ? "SIGNIFICANT" : "N.S."}
        </span>
        <b style={{ color: "var(--text)" }}>{res.test}</b>
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          · {featLabel} of {sigLabel} · {res.design} · {res.normal ? "normal" : "non-normal"}
        </span>
      </div>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        statistic = <b style={{ color: "var(--text)" }}>{fmt(res.statistic, 3)}</b>,
        p = <b style={{ color: "var(--text)" }}>{fmt(res.p, 4)}</b>
        {res.effect_size && <> · {res.effect_size.name} = {fmt(res.effect_size.value, 3)} ({res.effect_size.magnitude})</>}
      </div>
      {res.interpretation && <div className="text-xs" style={{ color: "var(--text-muted)" }}>{res.interpretation}</div>}

      <div className="grid gap-3 md:grid-cols-2">
        {/* plot (server-rendered matplotlib SVG) */}
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
            {featLabel} {sigLabel} by condition · violin + box
          </div>
          <img className="w-full rounded-lg bg-white" alt={`${featLabel} ${sigLabel} by condition`}
            src={analysisApi.plotUrl(plotBase, res.feature, "svg")} />
        </div>

        {/* descriptives + post-hoc */}
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Per condition</div>
          <table className="w-full text-[11px]">
            <thead><tr style={{ color: "var(--text-muted)" }}>
              <th className="text-left">Condition</th><th className="text-right">n</th>
              <th className="text-right">Mean</th><th className="text-right">SD</th><th className="text-right">Normal?</th>
            </tr></thead>
            <tbody>
              {res.descriptives?.map((d) => (
                <tr key={d.condition}>
                  <td style={{ color: "var(--text)" }}>{d.condition}</td>
                  <td className="tnum text-right">{d.n}</td>
                  <td className="tnum text-right">{fmt(d.mean)}</td>
                  <td className="tnum text-right">{fmt(d.sd)}</td>
                  <td className="tnum text-right">
                    {d.shapiro_p == null ? "—" : `${d.shapiro_p > 0.05 ? "✓" : "✗"} ${fmt(d.shapiro_p)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {res.posthoc && res.posthoc.length > 0 && (
            <div className="mt-2 text-[11px]" style={{ color: "var(--text-muted)" }}>
              <div className="text-[10px] uppercase tracking-wide">Post-hoc (Holm)</div>
              {res.posthoc.map((ph, i) => (
                <div key={i}>{ph.a} vs {ph.b}: p={fmt(ph.p_corr)} {ph.sig ? "✓" : ""}</div>
              ))}
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <a className="chip-dl" href={analysisApi.plotUrl(plotBase, res.feature, "svg")}>⬇ SVG</a>
            <a className="chip-dl" href={analysisApi.plotUrl(plotBase, res.feature, "pdf")}>⬇ PDF</a>
            <button className="chip-dl" onClick={() => downloadCsv(res)}>⬇ values CSV</button>
            <button className="chip-dl" onClick={() => downloadJson(res)}>⬇ JSON</button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add the `.chip-dl` utility class**

In `hri_monitor/ui/src/index.css`, append (after the existing layer/utility definitions — match the existing file's style; this is plain CSS that works with Tailwind v4):

```css
.chip-dl {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  color: var(--accent);
  border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
  background: transparent;
}
.chip-dl:hover { background: color-mix(in srgb, var(--accent) 12%, transparent); }
```

- [ ] **Step 3: Typecheck**

Run: `cd hri_monitor/ui && npx tsc --noEmit`
Expected: no errors. (`var(--ok)` is a Clinical Frost token; if it is absent in `index.css`, use `var(--accent)` instead — grep `index.css` for `--ok` first and fall back if missing.)

- [ ] **Step 4: Commit**

```bash
git add hri_monitor/ui/src/components/analysis/ResultBlock.tsx hri_monitor/ui/src/index.css
git commit -m "feat(analysis-ui): per-feature result block (verdict + plot + table + export)"
```

---

### Task 3: Analysis page (`pages/Analysis.tsx`) + control bar

**Files:**
- Create: `hri_monitor/ui/src/pages/Analysis.tsx`

- [ ] **Step 1: Implement the page**

Create `hri_monitor/ui/src/pages/Analysis.tsx`:

```typescript
import { useState } from "react";
import { ResultBlock } from "../components/analysis/ResultBlock";
import {
  type AnalysisResult, type CompareReq, analysisApi, useAnalysisOptions,
  FEATURE_LABELS, SIGNAL_LABELS,
} from "../lib/analysis";
import { useExperiments } from "../lib/experiments";

export function Analysis() {
  const { experiments } = useExperiments();
  const [expId, setExpId] = useState<number | null>(null);
  const options = useAnalysisOptions(expId);

  const [signal, setSignal] = useState<string>("");
  const [features, setFeatures] = useState<string[]>(["mean"]);
  const [condIds, setCondIds] = useState<number[]>([]);
  const [unit, setUnit] = useState<"participant" | "recording">("participant");
  const [results, setResults] = useState<AnalysisResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastReq, setLastReq] = useState<CompareReq | null>(null);

  const toggle = <T,>(arr: T[], v: T) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  const onPickExp = (id: number) => {
    setExpId(id); setSignal(""); setCondIds([]); setResults(null);
  };

  const canRun = expId != null && signal && features.length > 0 && condIds.length >= 2 && !busy;

  const run = async () => {
    if (expId == null) return;
    const req: CompareReq = { experiment_id: expId, condition_ids: condIds, signal, features, unit };
    setBusy(true); setLastReq(req);
    try {
      const r = await analysisApi.compare(req);
      setResults(r.results);
    } finally { setBusy(false); }
  };

  const lbl = { fontSize: 10, textTransform: "uppercase" as const, letterSpacing: "0.05em", color: "var(--text-muted)" };

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>Analysis</h2>

      {/* control bar */}
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
            <div style={lbl} className="mb-1">Signal</div>
            <select className="an-sel" value={signal} onChange={(e) => setSignal(e.target.value)}
              disabled={!options}>
              <option value="" disabled>Select…</option>
              {options?.signals.map((s) => <option key={s} value={s}>{SIGNAL_LABELS[s] ?? s}</option>)}
            </select>
          </div>
          <div>
            <div style={lbl} className="mb-1">Unit of analysis</div>
            <div className="flex gap-2">
              {(["participant", "recording"] as const).map((u) => (
                <button key={u} onClick={() => setUnit(u)}
                  className="rounded-full px-3 py-1 text-[11px] font-semibold"
                  style={unit === u
                    ? { background: "color-mix(in srgb, var(--accent) 18%, transparent)", color: "var(--accent)", border: "1px solid var(--accent)" }
                    : { color: "var(--text-muted)", border: "1px solid color-mix(in srgb, var(--text-muted) 30%, transparent)" }}>
                  {u === "participant" ? "Per participant" : "Per recording"}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div>
          <div style={lbl} className="mb-1">Features</div>
          <div className="flex flex-wrap gap-2">
            {options?.features.map((f) => (
              <button key={f} onClick={() => setFeatures((a) => toggle(a, f))}
                className="rounded-full px-3 py-1 text-[11px] font-semibold"
                style={features.includes(f)
                  ? { background: "color-mix(in srgb, var(--accent) 18%, transparent)", color: "var(--accent)", border: "1px solid var(--accent)" }
                  : { color: "var(--text-muted)", border: "1px solid color-mix(in srgb, var(--text-muted) 30%, transparent)" }}>
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
                className="rounded-full px-3 py-1 text-[11px] font-semibold"
                style={condIds.includes(c.id)
                  ? { background: "color-mix(in srgb, var(--accent) 18%, transparent)", color: "var(--accent)", border: "1px solid var(--accent)" }
                  : { color: "var(--text-muted)", border: "1px solid color-mix(in srgb, var(--text-muted) 30%, transparent)" }}>
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

      {/* results: one block per feature */}
      {results && lastReq && results.length === 0 && (
        <div className="glass p-4 text-sm" style={{ color: "var(--text-muted)" }}>No results.</div>
      )}
      {results && lastReq && results.map((res, i) => (
        <ResultBlock key={`${res.feature}-${i}`} res={res} req={lastReq} />
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Add the `.an-sel` select style**

In `hri_monitor/ui/src/index.css`, append:

```css
.an-sel {
  width: 100%;
  background: color-mix(in srgb, var(--text-muted) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--text-muted) 25%, transparent);
  border-radius: 8px;
  color: var(--text);
  padding: 5px 8px;
  font-size: 12px;
}
.an-sel:disabled { opacity: 0.5; }
```

- [ ] **Step 3: Typecheck**

Run: `cd hri_monitor/ui && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add hri_monitor/ui/src/pages/Analysis.tsx hri_monitor/ui/src/index.css
git commit -m "feat(analysis-ui): analysis page with control bar + multi-feature results"
```

---

### Task 4: Mount the page in `App.tsx`

**Files:**
- Modify: `hri_monitor/ui/src/App.tsx`

- [ ] **Step 1: Import and render Analysis**

In `hri_monitor/ui/src/App.tsx`, add the import near the other page imports:

```typescript
import { Analysis } from "./pages/Analysis";
```

Then change the main render so the `Analysis` page renders. Replace this block:

```typescript
        ) : page === "Experiments" ? (
          <Experiments />
        ) : (
```

with:

```typescript
        ) : page === "Experiments" ? (
          <Experiments />
        ) : page === "Analysis" ? (
          <Analysis />
        ) : (
```

- [ ] **Step 2: Typecheck + build**

Run: `cd hri_monitor/ui && npx tsc --noEmit && npm run build`
Expected: build succeeds, writes to `../ui_dist`.

- [ ] **Step 3: Commit (source + built bundle)**

```bash
git add hri_monitor/ui/src/App.tsx hri_monitor/ui_dist
git commit -m "feat(analysis-ui): mount Analysis page + rebuild ui bundle"
```

---

### Task 5: Manual end-to-end verification

**Files:** none (verification).

- [ ] **Step 1: Run the app against your real data**

```bash
cd hri_monitor && .venv/bin/python run.py
```

Open the browser (or the URL it prints). Click **Analysis** in the sidebar.

- [ ] **Step 2: Drive one comparison**

- Pick your experiment → a signal that has data (e.g. GSR) → check **Mean** and **SD** → pick **≥2 conditions** that share participants → keep **Per participant** → **Run analysis**.
- Verify: two result blocks appear (Mean, SD); each shows a test name + p + effect size, a violin+box SVG with points, and the descriptives table with normality marks. `design` should read **paired** if the same participants are in every chosen condition.
- Switch unit to **Per recording**, Run again → blocks update; design now **unpaired**.
- If a condition has <3 observations, that feature's block shows the insufficient-data message (others still render).

- [ ] **Step 3: Verify exports**

- Click **⬇ SVG** and **⬇ PDF** on a block → both download and open as a clean violin+box figure.
- Click **⬇ JSON** → a JSON file with the full result downloads.
- Confirm the embedded plot image matches the downloaded SVG.

- [ ] **Step 4: Confirm read-only + clean**

```bash
git status --short    # only expected tracked changes; data/ untouched (gitignored)
```

Report: the Analysis page works end-to-end on real data; note the test selected, the p-value, and whether pairing was detected as expected. The milestone is complete.
