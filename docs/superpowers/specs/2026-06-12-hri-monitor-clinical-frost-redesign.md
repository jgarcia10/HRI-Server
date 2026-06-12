# HRI Monitor — "Clinical Frost" UI Redesign Spec

**Date:** 2026-06-12
**Status:** Approved pending user review
**Scope:** `hri_monitor/ui/` only (+ rebuilt `ui_dist/`, + new `hri_monitor/design_system/` bundle published to claude.ai/design). The Python hub is untouched.

## 1. Goal

Replace the milestone-1 placeholder styling with a complete design language — "Clinical Frost": a light-first liquid-glass aesthetic with a logo, light + dark themes, lucide icons, and modern gradient/glow charts. Additionally publish the design system to a claude.ai/design project so it can be browsed on the web.

## 2. Design language

### Tokens (semantic CSS variables; OKLCH where practical)

| Token | Light | Dark |
|---|---|---|
| base background | `#fbfdff` → `#eef6fb` gradient | `#0b1220` |
| texture | blueprint dot-grid, `rgba(14,165,233,.14)` 1px dots / 14px | same grid `rgba(125,170,220,.12)` |
| glass panel bg | `rgba(255,255,255,.65)` | `rgba(148,184,220,.08)` |
| glass border | `rgba(186,210,235,.8)` | `rgba(148,184,220,.18)` |
| glass blur | `blur(8px) saturate(160%)` | same |
| specular | `inset 0 1px 0 rgba(255,255,255,.95)` | `inset 0 1px 0 rgba(200,225,255,.15)` |
| outer shadow | `0 6px 20px rgba(14,60,110,.08)` | `0 6px 20px rgba(0,0,0,.3)` |
| text primary / muted | `#0c1a28` / `#5b7186` | `#eaf3fb` / `#7e93ad` |
| accent primary / secondary | sky `#0284c7` / teal `#0d9488` | sky `#38bdf8` / teal `#2dd4bf` |
| chart: GSR / PPG / blink / temp | `#0284c7` / `#e11d48` / `#7c3aed` / `#d97706` | `#38bdf8` / `#fb7185` / `#a78bfa` / `#fbbf24` |
| status ok / warn / err | emerald `#059669` / amber `#d97706` / rose `#e11d48` | `#34d399` / `#fbbf24` / `#fb7185` |

Radius: 16px cards (`rounded-2xl`), 12px inner elements. All components consume semantic variables — no `dark:` branching except one-offs.

### Typography
- **Geist Sans** (UI) + **Geist Mono** (live numeric readouts, `font-variant-numeric: tabular-nums`), self-hosted via Fontsource packages (offline lab requirement — no CDN fonts).
- Fallback stack: `system-ui, sans-serif` / `ui-monospace, monospace`.

### Icons
**lucide-react**, 2px stroke, per-icon imports. Mapping: Live→Activity, Devices→Cpu, Experiments→FlaskConical, Analysis→BarChart3, Models→Brain, Settings→Settings; GSR→Waves, PPG/HR→HeartPulse, blink→Eye, temperature→Thermometer, video→Video, theme→Sun/Moon, hub link→Wifi/WifiOff.

### Logo
Rounded hexagon (sensor cell) with a 2px round-cap pulse line through it; sky→teal `linearGradient` stroke; inline React SVG component with props `size` and `mono` (`currentColor`, for favicons/monochrome contexts). Used in sidebar header (with "HRI Monitor" wordmark), and as SVG favicon in `index.html`.

### Theme system
- `data-theme="light" | "dark"` on `<html>`; Tailwind v4 `@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *))`.
- Default = system preference; manual toggle (Sun/Moon button at sidebar bottom) overrides and persists to `localStorage("hri-theme")`; "system" is restored by removing the key (cycle: light → dark → system).
- Inline pre-paint script in `index.html` applies the attribute before first render (no flash); sets `color-scheme`.

### Discipline rules
- Glass only on chrome (sidebar, cards, tooltips) — never overlaying data; charts stay crisp/opaque.
- Blur ≤ 12px, ≤ 6 blurred surfaces per view; chips/badges use translucent solids without blur.
- `prefers-reduced-transparency`: solid `--surface` fallback, no backdrop-filter. `prefers-reduced-motion`: no pulse animations.
- Body text contrast ≥ 4.5:1 against worst-case backdrop in both themes.

## 3. Component architecture (`hri_monitor/ui/src/`)

| Unit | Responsibility |
|---|---|
| `index.css` | Tokens (`@theme` + `:root`/`[data-theme=dark]` variables), dark custom-variant, `.glass`/`.glass-strong` utilities with fallbacks, dot-grid background utility, font registration |
| `lib/theme.ts` | `useTheme()` hook: reads/writes localStorage + data-theme; exposes `{theme, resolved, cycle}` |
| `components/Logo.tsx` | Hex-pulse SVG mark (gradient / `mono` variants) |
| `components/SignalChart.tsx` | Recharts `AreaChart`: monotone curve, vertical gradient fill (unique id via `useId()`), horizontal-only dashed grid, no axis/tick lines, glass tooltip, header = lucide icon + title + Geist Mono tabular value |
| `components/StatusChip.tsx` | Translucent solid chip, glowing dot, pulse on `connected` (motion-safe) |
| `components/VideoFeed.tsx` | Glass frame, Video icon header, "no signal" empty state on img error |
| `App.tsx` | Frosted sidebar (logo, lucide nav, theme toggle), dot-grid background layer, glass top header on main area |
| `pages/Live.tsx` | Same layout as milestone 1, recomposed with new components |
| `index.html` | Title, SVG favicon, pre-paint theme script |

New npm deps: `lucide-react`, `@fontsource-variable/geist`, `@fontsource-variable/geist-mono` (or non-variable equivalents). No other library changes; Recharts stays.

Charts keep `isAnimationActive={false}`; glow (`feDropShadow`) is applied to strokes only and disabled on PPG (highest-rate trace) if profiling shows cost.

## 4. Design-system bundle + DesignSync publishing

- New folder `hri_monitor/design_system/` of self-contained static HTML previews (inline CSS, no build step), each starting with `<!-- @dsCard group="…" -->`:
  - `brand/logo.html` (mark variants, light/dark, mono), `foundations/colors.html` (both palettes), `foundations/typography.html`, `components/glass-cards.html`, `components/status-chips.html`, `components/charts.html` (static SVG renderings of the chart style), `components/sidebar.html`.
- Publish flow (after implementation is merged): `DesignSync list_projects` → create project **"HRI Monitor Design System"** if absent → `finalize_plan` (writes `**/*.html` under the bundle) → `write_files` from `hri_monitor/design_system/`.
- Repo is the source of truth; the claude.ai project is a pushed snapshot, re-pushed on future design changes. Publishing requires the user's claude.ai login to grant design scopes on first call.

## 5. Error handling / robustness

- Theme hook tolerates unavailable `localStorage` (private mode) — falls back to system, no crash.
- `VideoFeed` shows an explicit "no signal" glass state when the MJPEG img errors, with retry on click.
- All glass utilities ship the reduced-transparency/motion fallbacks in CSS (not JS).
- If DesignSync publishing fails (no login/scopes), the redesign itself is unaffected; report and let the user retry.

## 6. Testing & verification

- Python suite unchanged and must stay green (20 passed) — includes the static-serving test against the rebuilt `ui_dist`.
- `npm run build` succeeds; bundle inspected for self-hosted fonts (no external font URLs).
- Live verification against simulators (`python run.py`): both themes checked for — readable charts/values, status chips, video frames, toggle persistence across reload, no flash-of-wrong-theme.
- No JS unit-test runner added (YAGNI for one hook); theme behavior verified in the live smoke and documented in the plan.

## 7. Out of scope

- Redesign of not-yet-built pages (Devices/Experiments/Analysis/Models/Settings get the new shell + placeholder styling only; their content arrives in milestones 2–6 already in this language).
- Refraction/lensing SVG filters (Chromium-only; distorts data — deliberately excluded).
- Custom icon design beyond the logo; animation systems (Framer Motion); HTTPS/`wss:` support.
