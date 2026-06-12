# Clinical Frost UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reskin the HRI Monitor UI in the "Clinical Frost" design language — logo, light+dark themes with a no-flash toggle, lucide icons, Geist type, liquid-glass surfaces, gradient/glow charts — and publish the design system to claude.ai/design.

**Architecture:** Pure `hri_monitor/ui/` change (+ rebuilt `ui_dist/`, + new static `hri_monitor/design_system/` bundle). All theming flows through semantic CSS variables defined once in `index.css`; components consume `var(--token)` and never branch on theme. A `data-theme` attribute on `<html>` drives Tailwind v4's custom dark variant; a pre-paint script prevents theme flash. The Python hub is untouched.

**Tech Stack:** React 18, Vite 5, Tailwind v4, Recharts 2, lucide-react, Fontsource Geist (Sans + Mono variable). No new test runner: per-task verification is `npx tsc --noEmit` + `npm run build`; final verification is the live smoke in both themes + the existing 20-test Python suite.

**Spec:** `docs/superpowers/specs/2026-06-12-hri-monitor-clinical-frost-redesign.md`

**Working directory:** repo root unless stated. UI commands run from `hri_monitor/ui/`. Python commands use `hri_monitor/.venv`.

**Verification commands used by every UI task:**

```bash
cd hri_monitor/ui
npx tsc --noEmit     # type check (vite build does NOT typecheck)
npm run build        # must succeed; rebuilds ../ui_dist
```

---

### Task 1: Dependencies, design tokens, theme foundation

**Files:**
- Modify: `hri_monitor/ui/package.json`
- Rewrite: `hri_monitor/ui/index.html`
- Create: `hri_monitor/ui/public/favicon.svg`
- Rewrite: `hri_monitor/ui/src/index.css`
- Create: `hri_monitor/ui/src/lib/theme.ts`

- [ ] **Step 1: Add dependencies**

In `hri_monitor/ui/package.json`, add to `"dependencies"` (keep existing entries):

```json
    "@fontsource-variable/geist": "^5.2.5",
    "@fontsource-variable/geist-mono": "^5.2.5",
    "lucide-react": "^0.460.0",
```

Run: `cd hri_monitor/ui && npm install`
Expected: installs without error. If a version is unavailable, use the nearest available caret version and report the substitution.

- [ ] **Step 2: Rewrite `hri_monitor/ui/index.html`** (favicon + pre-paint theme script)

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <title>HRI Monitor</title>
    <script>
      (function () {
        try {
          var t = localStorage.getItem("hri-theme");
          if (t !== "light" && t !== "dark") {
            t = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
          }
          document.documentElement.dataset.theme = t;
        } catch (e) {
          document.documentElement.dataset.theme = "light";
        }
      })();
    </script>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 3: Create `hri_monitor/ui/public/favicon.svg`** (Vite copies `public/` into the build root)

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <defs><linearGradient id="g" x1="0" y1="0" x2="24" y2="24"><stop offset="0" stop-color="#0ea5e9"/><stop offset="1" stop-color="#14b8a6"/></linearGradient></defs>
  <path d="M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9L12 3z" stroke="url(#g)" stroke-width="2" stroke-linejoin="round"/>
  <path d="M7.5 12.5h2.5l2-3 2 5 1.5-2h1" stroke="url(#g)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
```

- [ ] **Step 4: Rewrite `hri_monitor/ui/src/index.css`** (the whole design system core)

```css
@import "tailwindcss";
@import "@fontsource-variable/geist";
@import "@fontsource-variable/geist-mono";

@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));

@theme {
  --font-sans: "Geist Variable", system-ui, sans-serif;
  --font-mono: "Geist Mono Variable", ui-monospace, monospace;
}

/* ---- Clinical Frost tokens (spec §2). Light is primary. ---- */
:root {
  color-scheme: light;
  --base: #fbfdff;
  --base-2: #eef6fb;
  --grid-dot: rgba(14, 165, 233, 0.14);
  --glass-bg: rgba(255, 255, 255, 0.65);
  --glass-border: rgba(186, 210, 235, 0.8);
  --glass-specular: rgba(255, 255, 255, 0.95);
  --glass-shadow: rgba(14, 60, 110, 0.08);
  --text: #0c1a28;
  --text-muted: #5b7186;
  --accent: #0284c7;
  --accent-2: #0d9488;
  --chart-gsr: #0284c7;
  --chart-ppg: #e11d48;
  --chart-blink: #7c3aed;
  --chart-temp: #d97706;
  --ok: #059669;
  --warn: #d97706;
  --err: #e11d48;
}

[data-theme="dark"] {
  color-scheme: dark;
  --base: #0b1220;
  --base-2: #0b1220;
  --grid-dot: rgba(125, 170, 220, 0.12);
  --glass-bg: rgba(148, 184, 220, 0.08);
  --glass-border: rgba(148, 184, 220, 0.18);
  --glass-specular: rgba(200, 225, 255, 0.15);
  --glass-shadow: rgba(0, 0, 0, 0.3);
  --text: #eaf3fb;
  --text-muted: #7e93ad;
  --accent: #38bdf8;
  --accent-2: #2dd4bf;
  --chart-gsr: #38bdf8;
  --chart-ppg: #fb7185;
  --chart-blink: #a78bfa;
  --chart-temp: #fbbf24;
  --ok: #34d399;
  --warn: #fbbf24;
  --err: #fb7185;
}

body {
  font-family: var(--font-sans);
  background: linear-gradient(135deg, var(--base), var(--base-2));
  color: var(--text);
  min-height: 100vh;
}

/* Frosted panel — chrome only, never over data (spec §2 discipline) */
@utility glass {
  background: var(--glass-bg);
  -webkit-backdrop-filter: blur(8px) saturate(160%);
  backdrop-filter: blur(8px) saturate(160%);
  border: 1px solid var(--glass-border);
  border-radius: 1rem;
  box-shadow: 0 6px 20px var(--glass-shadow), inset 0 1px 0 var(--glass-specular);
}

/* Blueprint dot-grid texture */
@utility dot-grid {
  background-image: radial-gradient(var(--grid-dot) 1px, transparent 1px);
  background-size: 14px 14px;
}

/* Tabular numerals for live readouts — values must not jitter */
@utility tnum {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

/* Glow on chart strokes; color injected per-chart via --glow-color */
.chart-glow .recharts-area-curve {
  filter: drop-shadow(0 0 3px var(--glow-color));
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Accessibility fallbacks (spec §2): solid surfaces, no pulse */
@media (prefers-reduced-transparency: reduce) {
  .glass {
    background: var(--base);
    -webkit-backdrop-filter: none;
    backdrop-filter: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .chart-glow .recharts-area-curve { filter: none; }
}
```

- [ ] **Step 5: Create `hri_monitor/ui/src/lib/theme.ts`**

```ts
import { useCallback, useEffect, useState } from "react";

export type ThemePref = "light" | "dark" | "system";
const KEY = "hri-theme";

function systemTheme(): "light" | "dark" {
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function storedPref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system"; // private mode: no persistence, system default
  }
}

/** Theme preference cycle: light → dark → system. "system" tracks the OS live. */
export function useTheme() {
  const [pref, setPref] = useState<ThemePref>(storedPref);
  const [sys, setSys] = useState<"light" | "dark">(systemTheme);
  const resolved = pref === "system" ? sys : pref;

  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setSys(mq.matches ? "dark" : "light");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = resolved;
    try {
      if (pref === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, pref);
    } catch {
      // private mode: theme applies but won't persist
    }
  }, [pref, resolved]);

  const cycle = useCallback(() => {
    setPref((p) => (p === "light" ? "dark" : p === "dark" ? "system" : "light"));
  }, []);

  return { pref, resolved, cycle };
}
```

- [ ] **Step 6: Verify**

Run: `cd hri_monitor/ui && npx tsc --noEmit && npm run build`
Expected: both succeed. (The app still uses old component styling — that's fine; tokens and utilities are now available. `theme.ts` is not imported yet; tsc still checks it via `include: ["src"]`.)

- [ ] **Step 7: Commit**

```bash
git add hri_monitor/ui/package.json hri_monitor/ui/package-lock.json hri_monitor/ui/index.html hri_monitor/ui/public/favicon.svg hri_monitor/ui/src/index.css hri_monitor/ui/src/lib/theme.ts
git commit -m "feat(ui): clinical frost tokens, theme system, fonts, favicon"
```

(Do NOT commit `ui_dist/` yet — it rebuilds with every task; it's committed once in Task 5.)

---

### Task 2: Logo component + app shell (sidebar, theme toggle)

**Files:**
- Create: `hri_monitor/ui/src/components/Logo.tsx`
- Rewrite: `hri_monitor/ui/src/App.tsx`

- [ ] **Step 1: Create `hri_monitor/ui/src/components/Logo.tsx`**

```tsx
const GRADIENT_ID = "hri-logo-gradient";

/** Hex-cell + pulse mark. `mono` renders in currentColor for monochrome contexts. */
export function Logo({ size = 28, mono = false }: { size?: number; mono?: boolean }) {
  const stroke = mono ? "currentColor" : `url(#${GRADIENT_ID})`;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-label="HRI Monitor logo">
      {!mono && (
        <defs>
          <linearGradient id={GRADIENT_ID} x1="0" y1="0" x2="24" y2="24">
            <stop offset="0" stopColor="#0ea5e9" />
            <stop offset="1" stopColor="#14b8a6" />
          </linearGradient>
        </defs>
      )}
      <path d="M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9L12 3z"
            stroke={stroke} strokeWidth="2" strokeLinejoin="round" />
      <path d="M7.5 12.5h2.5l2-3 2 5 1.5-2h1"
            stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
```

- [ ] **Step 2: Rewrite `hri_monitor/ui/src/App.tsx`**

```tsx
import {
  Activity, BarChart3, Brain, Cpu, FlaskConical, Monitor, Moon, Settings, Sun,
} from "lucide-react";
import { useState } from "react";
import { Logo } from "./components/Logo";
import { useTheme } from "./lib/theme";
import { Live } from "./pages/Live";

const PAGES = [
  { name: "Live", icon: Activity },
  { name: "Devices", icon: Cpu },
  { name: "Experiments", icon: FlaskConical },
  { name: "Analysis", icon: BarChart3 },
  { name: "Models", icon: Brain },
  { name: "Settings", icon: Settings },
] as const;
type Page = (typeof PAGES)[number]["name"];

export default function App() {
  const [page, setPage] = useState<Page>("Live");
  const { pref, resolved, cycle } = useTheme();
  const ThemeIcon = pref === "system" ? Monitor : resolved === "dark" ? Moon : Sun;

  return (
    <div className="dot-grid flex min-h-screen">
      <aside className="glass sticky top-0 m-3 flex h-[calc(100vh-1.5rem)] w-56 shrink-0 flex-col p-4">
        <div className="mb-6 flex items-center gap-2.5">
          <Logo size={30} />
          <div>
            <h1 className="text-base font-semibold leading-tight">HRI Monitor</h1>
            <p className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
              clinical frost
            </p>
          </div>
        </div>
        <nav className="space-y-1">
          {PAGES.map(({ name, icon: Icon }) => (
            <button
              key={name}
              onClick={() => setPage(name)}
              className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm transition-colors"
              style={
                page === name
                  ? { color: "var(--accent)", background: "color-mix(in srgb, var(--accent) 12%, transparent)" }
                  : { color: "var(--text-muted)" }
              }
            >
              <Icon size={16} /> {name}
            </button>
          ))}
        </nav>
        <button
          onClick={cycle}
          title={`Theme: ${pref} (click to change)`}
          className="mt-auto flex items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm"
          style={{ color: "var(--text-muted)" }}
        >
          <ThemeIcon size={16} /> Theme: {pref}
        </button>
      </aside>
      <main className="min-w-0 flex-1 p-6">
        {page === "Live" ? (
          <Live />
        ) : (
          <div className="glass flex h-40 items-center justify-center text-sm" style={{ color: "var(--text-muted)" }}>
            “{page}” arrives in a later milestone — already dressed in Clinical Frost.
          </div>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Verify**

Run: `cd hri_monitor/ui && npx tsc --noEmit && npm run build`
Expected: both succeed.

- [ ] **Step 4: Commit**

```bash
git add hri_monitor/ui/src/components/Logo.tsx hri_monitor/ui/src/App.tsx
git commit -m "feat(ui): hex-pulse logo and frosted sidebar shell with theme toggle"
```

---

### Task 3: StatusChip + VideoFeed redesign

**Files:**
- Rewrite: `hri_monitor/ui/src/components/StatusChip.tsx`
- Rewrite: `hri_monitor/ui/src/components/VideoFeed.tsx`

- [ ] **Step 1: Rewrite `hri_monitor/ui/src/components/StatusChip.tsx`**

```tsx
const STYLES: Record<string, { color: string; pulse?: boolean }> = {
  connected: { color: "var(--ok)", pulse: true },
  connecting: { color: "var(--warn)" },
  reconnecting: { color: "var(--warn)" },
  disabled: { color: "var(--text-muted)" },
};

/** Translucent solid (no blur — spec: small elements skip backdrop-filter). */
export function StatusChip({ name, status }: { name: string; status: string }) {
  const s = STYLES[status] ?? STYLES.disabled;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium"
      style={{ color: s.color, background: `color-mix(in srgb, ${s.color} 12%, transparent)` }}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          s.pulse ? "motion-safe:animate-[pulse-dot_2s_ease-in-out_infinite]" : ""
        }`}
        style={{ background: s.color, boxShadow: `0 0 6px ${s.color}` }}
      />
      {name} · {status}
    </span>
  );
}
```

- [ ] **Step 2: Rewrite `hri_monitor/ui/src/components/VideoFeed.tsx`**

```tsx
import { Video, VideoOff } from "lucide-react";
import { useState } from "react";

export function VideoFeed({ title, src }: { title: string; src: string }) {
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  return (
    <div className="glass p-4">
      <h3 className="mb-2 flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text-muted)" }}>
        <Video size={15} /> {title}
      </h3>
      {failed ? (
        <button
          onClick={() => {
            setFailed(false);
            setRetry((r) => r + 1);
          }}
          className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-xl text-sm"
          style={{
            color: "var(--text-muted)",
            background: "color-mix(in srgb, var(--text-muted) 8%, transparent)",
          }}
        >
          <VideoOff size={22} />
          No signal — click to retry
        </button>
      ) : (
        <img
          src={`${src}?r=${retry}`}
          alt={title}
          onError={() => setFailed(true)}
          className="aspect-video w-full rounded-xl bg-black/80 object-contain"
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify**

Run: `cd hri_monitor/ui && npx tsc --noEmit && npm run build`
Expected: both succeed.

- [ ] **Step 4: Commit**

```bash
git add hri_monitor/ui/src/components/StatusChip.tsx hri_monitor/ui/src/components/VideoFeed.tsx
git commit -m "feat(ui): glowing status chips and glass video feed with no-signal state"
```

---

### Task 4: SignalChart upgrade (gradient area + glow)

**Files:**
- Rewrite: `hri_monitor/ui/src/components/SignalChart.tsx`

- [ ] **Step 1: Rewrite `hri_monitor/ui/src/components/SignalChart.tsx`**

```tsx
import type { LucideIcon } from "lucide-react";
import { useId } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, YAxis } from "recharts";
import type { Point } from "../lib/ws";

export function SignalChart({
  title, unit, colorVar, icon: Icon, points, value, glow = true,
}: {
  title: string;
  unit: string;
  colorVar: string; // CSS variable name, e.g. "--chart-gsr"
  icon: LucideIcon;
  points: Point[];
  value?: number;
  glow?: boolean; // disable on the highest-rate trace if profiling shows cost (spec §3)
}) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const color = `var(${colorVar})`;
  return (
    <div className="glass p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text-muted)" }}>
          <Icon size={15} style={{ color }} /> {title}
        </h3>
        <span className="tnum text-xl font-semibold">
          {value !== undefined ? value.toFixed(2) : "—"}{" "}
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>{unit}</span>
        </span>
      </div>
      <div
        className={`h-24 ${glow ? "chart-glow" : ""}`}
        style={{ "--glow-color": color } as React.CSSProperties}
      >
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--glass-border)" strokeDasharray="3 3" vertical={false} />
            <YAxis domain={["auto", "auto"]} hide />
            <Area
              type="monotone"
              dataKey="v"
              stroke={color}
              strokeWidth={2}
              fill={`url(#${id})`}
              dot={false}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
```

Note: `import React from "react"` is NOT needed (jsx: react-jsx), but the `React.CSSProperties` type reference requires `import type React from "react"` — add `import type React from "react";` at the top if tsc complains.

- [ ] **Step 2: Verify**

Run: `cd hri_monitor/ui && npx tsc --noEmit && npm run build`
Expected: both succeed (Live.tsx still passes the old props — if tsc errors on Live.tsx's old `color=`/no-icon usage, that's expected ONLY if you ran this before Task 5; in that case proceed to Task 5 and verify both together, and say so in your report).

- [ ] **Step 3: Commit**

```bash
git add hri_monitor/ui/src/components/SignalChart.tsx
git commit -m "feat(ui): gradient-fill glow area charts with icon headers"
```

(If Step 2 deferred verification to Task 5, commit Tasks 4+5 together in Task 5 instead and note it.)

---

### Task 5: Live page recomposition, rebuild, live verification in both themes

**Files:**
- Rewrite: `hri_monitor/ui/src/pages/Live.tsx`
- Regenerate + commit: `hri_monitor/ui_dist/`

- [ ] **Step 1: Rewrite `hri_monitor/ui/src/pages/Live.tsx`**

```tsx
import { Eye, HeartPulse, Thermometer, Waves, Wifi, WifiOff } from "lucide-react";
import { SignalChart } from "../components/SignalChart";
import { StatusChip } from "../components/StatusChip";
import { VideoFeed } from "../components/VideoFeed";
import { useLiveData } from "../lib/ws";

export function Live() {
  const { latest, series, devices, connected } = useLiveData();
  const temps = latest["thermal.temps"];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium"
          style={{
            color: connected ? "var(--ok)" : "var(--warn)",
            background: `color-mix(in srgb, ${connected ? "var(--ok)" : "var(--warn)"} 12%, transparent)`,
          }}
        >
          {connected ? <Wifi size={13} /> : <WifiOff size={13} />} hub
        </span>
        {Object.entries(devices).map(([name, status]) => (
          <StatusChip key={name} name={name} status={status} />
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <VideoFeed title="Thermal" src="/stream/thermal" />
        <VideoFeed title="RGB" src="/stream/rgb" />
        <div className="glass p-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text-muted)" }}>
            <Thermometer size={15} /> Facial temperatures
          </h3>
          {temps ? (
            <dl className="grid grid-cols-2 gap-2 text-sm">
              {Object.entries(temps).map(([roi, v]) => (
                <div
                  key={roi}
                  className="flex justify-between rounded-lg px-2 py-1"
                  style={{ background: "color-mix(in srgb, var(--text-muted) 8%, transparent)" }}
                >
                  <dt style={{ color: "var(--text-muted)" }}>{roi.replace("_", " ")}</dt>
                  <dd className="tnum">{(v as number).toFixed(1)}°C</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>Waiting for thermal data…</p>
          )}
          <p className="mt-3 text-xs" style={{ color: "var(--text-muted)", opacity: 0.7 }}>
            Cognitive load & trust estimates arrive in milestone 3.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SignalChart title="GSR" unit="µS" colorVar="--chart-gsr" icon={Waves}
                     points={series["shimmer.gsr"] ?? []} value={latest["shimmer.gsr"]?.value} />
        <SignalChart title="PPG" unit="mV" colorVar="--chart-ppg" icon={HeartPulse} glow={false}
                     points={series["shimmer.ppg"] ?? []} value={latest["shimmer.ppg"]?.value} />
        <SignalChart title="Blink rate" unit="blinks/min" colorVar="--chart-blink" icon={Eye}
                     points={series["rgb.blink"] ?? []} value={latest["rgb.blink"]?.rate} />
        <SignalChart title="Forehead temp" unit="°C" colorVar="--chart-temp" icon={Thermometer}
                     points={series["thermal.temps"] ?? []} value={temps?.forehead} />
      </div>
    </div>
  );
}
```

(PPG gets `glow={false}` — it's the highest-rate trace; spec §3.)

- [ ] **Step 2: Type-check and rebuild**

Run: `cd hri_monitor/ui && npx tsc --noEmit && npm run build && test -f ../ui_dist/index.html && echo BUILD_OK`
Expected: `BUILD_OK`.

- [ ] **Step 3: Check fonts are self-hosted**

Run: `grep -rE "fonts.googleapis|fonts.gstatic" hri_monitor/ui_dist/ || echo NO_CDN_FONTS`
Expected: `NO_CDN_FONTS`. Also: `ls hri_monitor/ui_dist/assets | grep -ci woff` ≥ 1 (bundled font files).

- [ ] **Step 4: Live verification, both themes**

```bash
cd hri_monitor && .venv/bin/python run.py --no-browser &
sleep 4
curl -s http://127.0.0.1:8000/ | grep -o "<title>HRI Monitor</title>"
curl -s http://127.0.0.1:8000/favicon.svg | head -c 60
kill %1
```

Expected: title found; favicon SVG content returned. Then ask the human (or report for the controller to relay): open http://127.0.0.1:8000, confirm — frosted sidebar with logo; dot-grid background; 4 gradient area charts updating; status chips with pulsing green dots; theme button cycles light → dark → system with no flash on reload and persistence across reloads.

- [ ] **Step 5: Python regression**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests -q`
Expected: 20 passed.

- [ ] **Step 6: Commit (include rebuilt ui_dist)**

```bash
git add hri_monitor/ui/src/pages/Live.tsx hri_monitor/ui_dist
git commit -m "feat(ui): clinical frost live page; rebuild ui_dist"
```

---

### Task 6: Design-system bundle (static previews for claude.ai/design)

**Files (all new, all self-contained HTML with inline CSS, each starting with an `@dsCard` marker):**
- Create: `hri_monitor/design_system/brand/logo.html`
- Create: `hri_monitor/design_system/foundations/colors.html`
- Create: `hri_monitor/design_system/foundations/typography.html`
- Create: `hri_monitor/design_system/components/glass-cards.html`
- Create: `hri_monitor/design_system/components/status-chips.html`
- Create: `hri_monitor/design_system/components/charts.html`
- Create: `hri_monitor/design_system/components/sidebar.html`

All seven files share this base skeleton — reuse it verbatim, swapping the marker line, `<title>`, and the `<body>` content shown per file:

```html
<!-- @dsCard group="GROUP" -->
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>TITLE — HRI Monitor DS</title>
<style>
  :root { --sky:#0284c7; --teal:#0d9488; --ok:#059669; --warn:#d97706; --err:#e11d48; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:"Geist Variable",system-ui,sans-serif; padding:20px; background:#fbfdff; color:#0c1a28; }
  h1 { font-size:15px; margin:0 0 12px; }
  .row { display:flex; gap:16px; flex-wrap:wrap; }
  .tile { border-radius:14px; padding:16px; flex:1; min-width:260px; position:relative; overflow:hidden; }
  .tile.light { background:linear-gradient(135deg,#fbfdff,#eef6fb); border:1px solid #e3edf6; }
  .tile.dark  { background:#0b1220; color:#eaf3fb; }
  .dots-l { background-image:radial-gradient(rgba(14,165,233,.14) 1px,transparent 1px); background-size:14px 14px; }
  .dots-d { background-image:radial-gradient(rgba(125,170,220,.12) 1px,transparent 1px); background-size:14px 14px; }
  .glass-l { background:rgba(255,255,255,.65); backdrop-filter:blur(8px) saturate(160%); -webkit-backdrop-filter:blur(8px) saturate(160%); border:1px solid rgba(186,210,235,.8); border-radius:16px; box-shadow:0 6px 20px rgba(14,60,110,.08), inset 0 1px 0 rgba(255,255,255,.95); padding:14px; }
  .glass-d { background:rgba(148,184,220,.08); backdrop-filter:blur(8px) saturate(160%); -webkit-backdrop-filter:blur(8px) saturate(160%); border:1px solid rgba(148,184,220,.18); border-radius:16px; box-shadow:0 6px 20px rgba(0,0,0,.3), inset 0 1px 0 rgba(200,225,255,.15); padding:14px; }
  .muted-l { color:#5b7186; } .muted-d { color:#7e93ad; }
  .lbl { font-size:10px; text-transform:uppercase; letter-spacing:.05em; }
</style>
</head>
<body>
BODY
</body>
</html>
```

- [ ] **Step 1: `brand/logo.html`** — marker `<!-- @dsCard group="Brand" -->`, title `Logo`, body:

```html
<h1>Logo — hex-cell + pulse (sky→teal gradient stroke; monochrome-safe)</h1>
<svg width="0" height="0"><defs><linearGradient id="g" x1="0" y1="0" x2="24" y2="24"><stop offset="0" stop-color="#0ea5e9"/><stop offset="1" stop-color="#14b8a6"/></linearGradient></defs></svg>
<div class="row">
  <div class="tile light" style="display:flex;gap:24px;align-items:center;justify-content:center">
    <svg width="64" height="64" viewBox="0 0 24 24" fill="none"><path d="M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9L12 3z" stroke="url(#g)" stroke-width="2" stroke-linejoin="round"/><path d="M7.5 12.5h2.5l2-3 2 5 1.5-2h1" stroke="url(#g)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" style="color:#0c1a28"><path d="M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9L12 3z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M7.5 12.5h2.5l2-3 2 5 1.5-2h1" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    <div><div style="font-weight:700;font-size:20px">HRI Monitor</div><div class="lbl muted-l">clinical frost</div></div>
  </div>
  <div class="tile dark" style="display:flex;gap:24px;align-items:center;justify-content:center">
    <svg width="64" height="64" viewBox="0 0 24 24" fill="none"><path d="M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9L12 3z" stroke="url(#g)" stroke-width="2" stroke-linejoin="round"/><path d="M7.5 12.5h2.5l2-3 2 5 1.5-2h1" stroke="url(#g)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" style="color:#eaf3fb"><path d="M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9L12 3z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M7.5 12.5h2.5l2-3 2 5 1.5-2h1" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    <div><div style="font-weight:700;font-size:20px">HRI Monitor</div><div class="lbl muted-d">clinical frost</div></div>
  </div>
</div>
```

- [ ] **Step 2: `foundations/colors.html`** — marker `<!-- @dsCard group="Foundations" -->`, title `Colors`, body (one swatch helper + both palettes; copy exactly):

```html
<h1>Color tokens — light / dark</h1>
<style>
  .sw { width:120px; border-radius:10px; overflow:hidden; border:1px solid rgba(127,127,127,.2); font-size:10px; }
  .sw b { display:block; height:44px; }
  .sw span { display:block; padding:4px 6px; }
</style>
<div class="row" style="margin-bottom:14px">
  <div class="sw"><b style="background:#fbfdff"></b><span>base #fbfdff</span></div>
  <div class="sw"><b style="background:#0284c7"></b><span>accent/GSR #0284c7</span></div>
  <div class="sw"><b style="background:#0d9488"></b><span>accent-2 #0d9488</span></div>
  <div class="sw"><b style="background:#e11d48"></b><span>PPG/err #e11d48</span></div>
  <div class="sw"><b style="background:#7c3aed"></b><span>blink #7c3aed</span></div>
  <div class="sw"><b style="background:#d97706"></b><span>temp/warn #d97706</span></div>
  <div class="sw"><b style="background:#059669"></b><span>ok #059669</span></div>
  <div class="sw"><b style="background:#0c1a28"></b><span>text #0c1a28</span></div>
</div>
<div class="row" style="background:#0b1220;border-radius:14px;padding:14px">
  <div class="sw"><b style="background:#0b1220;border-bottom:1px solid #233"></b><span style="color:#eaf3fb">base #0b1220</span></div>
  <div class="sw"><b style="background:#38bdf8"></b><span style="color:#eaf3fb">accent/GSR #38bdf8</span></div>
  <div class="sw"><b style="background:#2dd4bf"></b><span style="color:#eaf3fb">accent-2 #2dd4bf</span></div>
  <div class="sw"><b style="background:#fb7185"></b><span style="color:#eaf3fb">PPG/err #fb7185</span></div>
  <div class="sw"><b style="background:#a78bfa"></b><span style="color:#eaf3fb">blink #a78bfa</span></div>
  <div class="sw"><b style="background:#fbbf24"></b><span style="color:#eaf3fb">temp/warn #fbbf24</span></div>
  <div class="sw"><b style="background:#34d399"></b><span style="color:#eaf3fb">ok #34d399</span></div>
  <div class="sw"><b style="background:#eaf3fb"></b><span style="color:#eaf3fb">text #eaf3fb</span></div>
</div>
```

- [ ] **Step 3: `foundations/typography.html`** — marker `<!-- @dsCard group="Foundations" -->`, title `Typography`, body:

```html
<h1>Typography — Geist Sans (UI) · Geist Mono tabular (live values)</h1>
<div class="row">
  <div class="tile light">
    <div style="font-size:22px;font-weight:650">Heading — Geist 650</div>
    <div style="font-size:14px;margin:6px 0">Body text — Geist 400. Physiological monitoring for human-robot interaction.</div>
    <div class="lbl muted-l">label — uppercase tracking-wide</div>
    <div style="font-family:'Geist Mono Variable',ui-monospace,monospace;font-variant-numeric:tabular-nums;font-size:26px;font-weight:650;margin-top:8px">4.21 <span style="font-size:12px;color:#0284c7">µS</span> · 72.04 <span style="font-size:12px;color:#e11d48">bpm</span></div>
    <div class="lbl muted-l" style="margin-top:4px">tabular-nums: digits never jitter while streaming</div>
  </div>
</div>
```

- [ ] **Step 4: `components/glass-cards.html`** — marker `<!-- @dsCard group="Components" -->`, title `Glass cards`, body:

```html
<h1>Glass cards — frosted chrome over dot-grid (blur 8px · saturate 160% · specular top edge)</h1>
<div class="row">
  <div class="tile light dots-l"><div class="glass-l">
    <div class="lbl muted-l">GSR</div>
    <div style="font-family:ui-monospace,monospace;font-variant-numeric:tabular-nums;font-size:22px;font-weight:650">4.21 <span style="font-size:11px;color:#0284c7">µS</span></div>
    <svg width="100%" height="40" viewBox="0 0 100 30" preserveAspectRatio="none"><defs><linearGradient id="f1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0284c7" stop-opacity=".3"/><stop offset="1" stop-color="#0284c7" stop-opacity="0"/></linearGradient></defs><path d="M0 22 C12 20 18 10 30 12 S52 26 64 18 86 6 100 10 L100 30 0 30Z" fill="url(#f1)"/><path d="M0 22 C12 20 18 10 30 12 S52 26 64 18 86 6 100 10" stroke="#0284c7" stroke-width="2" fill="none"/></svg>
  </div></div>
  <div class="tile dark dots-d"><div class="glass-d">
    <div class="lbl muted-d">GSR</div>
    <div style="font-family:ui-monospace,monospace;font-variant-numeric:tabular-nums;font-size:22px;font-weight:650">4.21 <span style="font-size:11px;color:#38bdf8">µS</span></div>
    <svg width="100%" height="40" viewBox="0 0 100 30" preserveAspectRatio="none"><defs><linearGradient id="f2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#38bdf8" stop-opacity=".35"/><stop offset="1" stop-color="#38bdf8" stop-opacity="0"/></linearGradient></defs><path d="M0 22 C12 20 18 10 30 12 S52 26 64 18 86 6 100 10 L100 30 0 30Z" fill="url(#f2)"/><path d="M0 22 C12 20 18 10 30 12 S52 26 64 18 86 6 100 10" stroke="#38bdf8" stroke-width="2" fill="none" style="filter:drop-shadow(0 0 3px rgba(56,189,248,.7))"/></svg>
  </div></div>
</div>
```

- [ ] **Step 5: `components/status-chips.html`** — marker `<!-- @dsCard group="Components" -->`, title `Status chips`, body:

```html
<h1>Status chips — translucent solid, glowing dot, pulse on connected</h1>
<style>
  .chip { display:inline-flex; align-items:center; gap:6px; font-size:11px; font-weight:600; border-radius:999px; padding:4px 10px; margin:3px; }
  .chip i { width:6px; height:6px; border-radius:999px; display:inline-block; }
  @keyframes p { 0%,100%{opacity:1} 50%{opacity:.4} }
</style>
<div class="row">
  <div class="tile light">
    <span class="chip" style="color:#059669;background:rgba(5,150,105,.12)"><i style="background:#059669;box-shadow:0 0 6px #059669;animation:p 2s infinite"></i>thermal · connected</span>
    <span class="chip" style="color:#d97706;background:rgba(217,119,6,.12)"><i style="background:#d97706"></i>shimmer · reconnecting</span>
    <span class="chip" style="color:#5b7186;background:rgba(91,113,134,.12)"><i style="background:#5b7186"></i>rgb · disabled</span>
  </div>
  <div class="tile dark">
    <span class="chip" style="color:#34d399;background:rgba(52,211,153,.14)"><i style="background:#34d399;box-shadow:0 0 6px #34d399;animation:p 2s infinite"></i>thermal · connected</span>
    <span class="chip" style="color:#fbbf24;background:rgba(251,191,36,.14)"><i style="background:#fbbf24"></i>shimmer · reconnecting</span>
    <span class="chip" style="color:#7e93ad;background:rgba(126,147,173,.14)"><i style="background:#7e93ad"></i>rgb · disabled</span>
  </div>
</div>
```

- [ ] **Step 6: `components/charts.html`** — marker `<!-- @dsCard group="Components" -->`, title `Charts`, body (four signal colors, light tile + dark tile; reuse the SVG area pattern from Step 4 with these stroke/gradient colors — light: `#0284c7`, `#e11d48`, `#7c3aed`, `#d97706`; dark: `#38bdf8`, `#fb7185`, `#a78bfa`, `#fbbf24`; each `<linearGradient>` id unique, e.g. `c1..c8`; label each mini-chart GSR / PPG / Blink / Temp using `.lbl`):

```html
<h1>Chart style — monotone area, vertical gradient fill, glow stroke (dark), dashed horizontal grid</h1>
<div class="row">
  <div class="tile light dots-l" style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
    <!-- four .glass-l mini-charts: GSR #0284c7 (c1), PPG #e11d48 (c2), Blink #7c3aed (c3), Temp #d97706 (c4) -->
  </div>
  <div class="tile dark dots-d" style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
    <!-- four .glass-d mini-charts: GSR #38bdf8 (c5), PPG #fb7185 (c6), Blink #a78bfa (c7), Temp #fbbf24 (c8); add drop-shadow glow on strokes except PPG -->
  </div>
</div>
```

Each mini-chart is exactly this block with COLOR/ID/LABEL substituted (this is the complete pattern — repeat it 8 times):

```html
<div class="glass-l"><div class="lbl muted-l">LABEL</div>
<svg width="100%" height="36" viewBox="0 0 100 30" preserveAspectRatio="none"><defs><linearGradient id="ID" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="COLOR" stop-opacity=".3"/><stop offset="1" stop-color="COLOR" stop-opacity="0"/></linearGradient></defs><path d="M0 22 C12 20 18 10 30 12 S52 26 64 18 86 6 100 10 L100 30 0 30Z" fill="url(#ID)"/><path d="M0 22 C12 20 18 10 30 12 S52 26 64 18 86 6 100 10" stroke="COLOR" stroke-width="2" fill="none"/></svg></div>
```

- [ ] **Step 7: `components/sidebar.html`** — marker `<!-- @dsCard group="Components" -->`, title `Sidebar`, body:

```html
<h1>Sidebar — frosted nav with logo, active accent tint, theme toggle</h1>
<svg width="0" height="0"><defs><linearGradient id="g" x1="0" y1="0" x2="24" y2="24"><stop offset="0" stop-color="#0ea5e9"/><stop offset="1" stop-color="#14b8a6"/></linearGradient></defs></svg>
<style>.nav{font-size:12px;border-radius:10px;padding:7px 10px;display:flex;gap:8px;align-items:center}</style>
<div class="row">
  <div class="tile light dots-l"><div class="glass-l" style="width:190px">
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px">
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none"><path d="M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9L12 3z" stroke="url(#g)" stroke-width="2" stroke-linejoin="round"/><path d="M7.5 12.5h2.5l2-3 2 5 1.5-2h1" stroke="url(#g)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <div><b style="font-size:13px">HRI Monitor</b><div class="lbl muted-l">clinical frost</div></div>
    </div>
    <div class="nav" style="color:#0284c7;background:rgba(2,132,199,.12)">▸ Live</div>
    <div class="nav muted-l">▸ Devices</div>
    <div class="nav muted-l">▸ Experiments</div>
    <div class="nav muted-l" style="margin-top:14px">◐ Theme: system</div>
  </div></div>
  <div class="tile dark dots-d"><div class="glass-d" style="width:190px">
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px">
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none"><path d="M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9L12 3z" stroke="url(#g)" stroke-width="2" stroke-linejoin="round"/><path d="M7.5 12.5h2.5l2-3 2 5 1.5-2h1" stroke="url(#g)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <div><b style="font-size:13px">HRI Monitor</b><div class="lbl muted-d">clinical frost</div></div>
    </div>
    <div class="nav" style="color:#38bdf8;background:rgba(56,189,248,.12)">▸ Live</div>
    <div class="nav muted-d">▸ Devices</div>
    <div class="nav muted-d">▸ Experiments</div>
    <div class="nav muted-d" style="margin-top:14px">◐ Theme: system</div>
  </div></div>
</div>
```

- [ ] **Step 8: Verify previews render**

Run: `ls hri_monitor/design_system/brand hri_monitor/design_system/foundations hri_monitor/design_system/components` (7 files) and `head -1 hri_monitor/design_system/**/*.html | grep -c dsCard` → every file's first line is the `@dsCard` marker. Open one in a browser if available; otherwise verify each file is valid standalone HTML (starts with marker, has doctype, no external references except none).

- [ ] **Step 9: Commit**

```bash
git add hri_monitor/design_system
git commit -m "feat(design): clinical frost design-system preview bundle"
```

---

### Task 7: Publish design system to claude.ai/design (CONTROLLER-EXECUTED)

**This task is executed by the controller in the main session, NOT a subagent** — DesignSync calls require the user's claude.ai login and interactive permission prompts.

- [ ] **Step 1:** `DesignSync list_projects` — if a project named "HRI Monitor Design System" exists and is writable, use its projectId (verify `get_project` shows `type: PROJECT_TYPE_DESIGN_SYSTEM`); otherwise `DesignSync create_project` with name `HRI Monitor Design System`.
- [ ] **Step 2:** `DesignSync finalize_plan` with `projectId`, `localDir: "<repo>/hri_monitor/design_system"`, `writes: ["brand/**/*.html", "foundations/**/*.html", "components/**/*.html"]`, no deletes.
- [ ] **Step 3:** `DesignSync write_files` with the planId and the 7 files via `localPath` (paths relative to localDir, e.g. `{path: "brand/logo.html", localPath: "brand/logo.html"}`).
- [ ] **Step 4:** Report the project URL/name to the user. If auth/scopes fail, report and continue — publishing is retryable and independent of the app redesign (spec §5).

---

### Task 8: Final regression + smoke

- [ ] **Step 1:** `cd hri_monitor && .venv/bin/python -m pytest tests -q` → 20 passed.
- [ ] **Step 2:** e2e smoke:

```bash
cd hri_monitor && .venv/bin/python run.py --no-browser &
sleep 4
curl -s http://127.0.0.1:8000/api/status
curl -s http://127.0.0.1:8000/ | grep -c "HRI Monitor"
curl -s -m 2 http://127.0.0.1:8000/stream/thermal | head -c 20 | grep -c frame
kill %1
```

Expected: three sensors connected; count ≥ 1; `1`.
- [ ] **Step 3:** `git status --short` → clean. Report milestone complete.
