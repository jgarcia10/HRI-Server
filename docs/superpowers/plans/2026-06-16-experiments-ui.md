# Experiments UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Clinical Frost Experiments page with three tabs — Manage (experiments/conditions/marker-labels/participants), Run (live recording console with condition chips, Start/Stop, record bar, live signal charts, marker panel), and Browse (sessions + CSV/zip export) — hitting the experiments backend API.

**Architecture:** `lib/experiments.ts` (typed API client + `useExperiments`/`useExperiment`/`useActiveRecording` hooks; the Run console reuses the existing `useLiveData()` from `lib/ws.ts` for live signal values). Page composed from small components. Clinical Frost tokens + existing `SignalChart`/`StatusChip` only.

**Tech Stack:** React 18, Vite 5, Tailwind v4, lucide-react. Verify: `npx tsc --noEmit` + `npm run build`, then live against the backend. Do NOT commit `ui_dist` until the final task.

**Spec:** `docs/superpowers/specs/2026-06-16-hri-monitor-experiments.md` §7.
**Prerequisite:** the experiments backend plan is merged (API endpoints exist).

**Working dir:** `hri_monitor/ui` for UI commands; `hri_monitor` for live checks.

---

### Task 1: API client + hooks (`lib/experiments.ts`)

**Files:** Create `hri_monitor/ui/src/lib/experiments.ts`

- [ ] **Step 1: Implement**

Create `hri_monitor/ui/src/lib/experiments.ts`:

```ts
import { useCallback, useEffect, useRef, useState } from "react";

export type Condition = { id: number; name: string; order_index: number };
export type MarkerLabel = { id: number; label: string };
export type Experiment = {
  id: number; name: string; description: string;
  conditions: Condition[]; marker_labels: MarkerLabel[];
};
export type Participant = { id: number; code: string; notes: string };
export type Marker = { id: number; t_offset: number; label: string; source: string };
export type Recording = {
  id: number; condition_id: number; started_at: number; stopped_at: number | null;
  sample_count: number; status: string; marker_count?: number;
};
export type Session = {
  id: number; participant_id: number; started_at: number; recordings: Recording[];
};
export type ActiveStatus = {
  recording_id: number; session_id: number; condition: string;
  elapsed: number; sample_count: number; markers: Marker[];
} | null;

async function j<T>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(url, opts);
  return r.json();
}
const post = (url: string, body?: unknown) =>
  j(url, { method: "POST", headers: { "Content-Type": "application/json" },
           body: body ? JSON.stringify(body) : undefined });

export const api = {
  listExperiments: () => j<Experiment[]>("/api/experiments"),
  getExperiment: (id: number) => j<Experiment>(`/api/experiments/${id}`),
  createExperiment: (name: string, description = "") =>
    post("/api/experiments", { name, description }) as Promise<{ id: number }>,
  deleteExperiment: (id: number) => fetch(`/api/experiments/${id}`, { method: "DELETE" }),
  setConditions: (id: number, conditions: string[]) =>
    fetch(`/api/experiments/${id}/conditions`, { method: "PUT",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ conditions }) }),
  setMarkerLabels: (id: number, labels: string[]) =>
    fetch(`/api/experiments/${id}/marker-labels`, { method: "PUT",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ labels }) }),
  listParticipants: (id: number) => j<Participant[]>(`/api/experiments/${id}/participants`),
  createParticipant: (id: number, code: string, notes = "") =>
    post(`/api/experiments/${id}/participants`, { code, notes }) as Promise<{ id: number }>,
  listSessions: (id: number) => j<Session[]>(`/api/experiments/${id}/sessions`),
  start: (body: { condition_id: number; experiment_id?: number; participant_id?: number; session_id?: number }) =>
    post("/api/recordings/start", body),
  marker: (recId: number, label: string, source: string) =>
    post(`/api/recordings/${recId}/marker`, { label, source }),
  stop: (recId: number) => post(`/api/recordings/${recId}/stop`),
};

export function useExperiments() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const refresh = useCallback(async () => setExperiments(await api.listExperiments()), []);
  useEffect(() => { refresh(); }, [refresh]);
  return { experiments, refresh };
}

export function useExperiment(id: number | null) {
  const [exp, setExp] = useState<Experiment | null>(null);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const refresh = useCallback(async () => {
    if (id == null) { setExp(null); setParticipants([]); return; }
    setExp(await api.getExperiment(id));
    setParticipants(await api.listParticipants(id));
  }, [id]);
  useEffect(() => { refresh(); }, [refresh]);
  return { exp, participants, refresh };
}

export function useActiveRecording() {
  const [active, setActive] = useState<ActiveStatus>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => {
    let stopped = false;
    const loop = async () => {
      try { setActive(await j<ActiveStatus>("/api/recordings/active")); } catch { /* keep */ }
      if (!stopped) timer.current = setTimeout(loop, 1000);
    };
    loop();
    return () => { stopped = true; if (timer.current) clearTimeout(timer.current); };
  }, []);
  return active;
}
```

- [ ] **Step 2: Verify** `cd hri_monitor/ui && npx tsc --noEmit` → clean.

- [ ] **Step 3: Commit**

```bash
git add hri_monitor/ui/src/lib/experiments.ts
git commit -m "feat(ui): experiments api client + hooks"
```

---

### Task 2: Manage tab (`components/exp/ManageTab.tsx`)

**Files:** Create `hri_monitor/ui/src/components/exp/ManageTab.tsx`

- [ ] **Step 1: Implement**

Create `hri_monitor/ui/src/components/exp/ManageTab.tsx`:

```tsx
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { api, type Experiment, type Participant } from "../../lib/experiments";
import { Field } from "../DeviceCard";

export function ManageTab({
  experiments, selected, onSelect, exp, participants, refresh, refreshList,
}: {
  experiments: Experiment[];
  selected: number | null;
  onSelect: (id: number | null) => void;
  exp: Experiment | null;
  participants: Participant[];
  refresh: () => void;
  refreshList: () => void;
}) {
  const [newExp, setNewExp] = useState("");
  const [condText, setCondText] = useState("");
  const [labelText, setLabelText] = useState("");
  const [pcode, setPcode] = useState("");

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="glass p-4">
        <h3 className="mb-2 text-sm font-medium" style={{ color: "var(--text-muted)" }}>Experiments</h3>
        <div className="space-y-1">
          {experiments.map((e) => (
            <button key={e.id} onClick={() => onSelect(e.id)}
              className="block w-full rounded-lg px-3 py-2 text-left text-sm"
              style={selected === e.id
                ? { color: "var(--accent)", background: "color-mix(in srgb, var(--accent) 12%, transparent)" }
                : { color: "var(--text)" }}>
              {e.name}
            </button>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <input className="flex-1 rounded-lg border px-2 py-1 text-xs" value={newExp}
            onChange={(e) => setNewExp(e.target.value)} placeholder="New experiment name"
            style={{ borderColor: "var(--glass-border)", background: "var(--glass-bg)", color: "var(--text)" }} />
          <button onClick={async () => { if (newExp.trim()) { const r: any = await api.createExperiment(newExp.trim()); setNewExp(""); refreshList(); onSelect(r.id); } }}
            className="rounded-lg px-3 text-xs font-semibold" style={{ background: "var(--accent)", color: "#fff" }}>
            <Plus size={14} />
          </button>
        </div>
      </div>

      {exp && (
        <div className="glass p-4 lg:col-span-2 space-y-3">
          <h3 className="text-sm font-medium" style={{ color: "var(--text)" }}>{exp.name}</h3>
          <Field label="Conditions">
            <div className="flex gap-2">
              <input className="flex-1 rounded-lg border px-2 py-1 text-xs"
                defaultValue={exp.conditions.map((c) => c.name).join(", ")}
                onBlur={(e) => setCondText(e.target.value)}
                placeholder="Comma-separated, in order"
                style={{ borderColor: "var(--glass-border)", background: "var(--glass-bg)", color: "var(--text)" }} />
              <button onClick={async () => { await api.setConditions(exp.id, (condText || exp.conditions.map(c=>c.name).join(",")).split(",").map(s => s.trim()).filter(Boolean)); refresh(); }}
                className="rounded-lg px-3 text-xs font-semibold" style={{ color: "var(--accent)", background: "color-mix(in srgb, var(--accent) 12%, transparent)" }}>Save</button>
            </div>
          </Field>
          <Field label="Marker labels">
            <div className="flex gap-2">
              <input className="flex-1 rounded-lg border px-2 py-1 text-xs"
                defaultValue={exp.marker_labels.map((l) => l.label).join(", ")}
                onBlur={(e) => setLabelText(e.target.value)}
                placeholder="Comma-separated quick-buttons"
                style={{ borderColor: "var(--glass-border)", background: "var(--glass-bg)", color: "var(--text)" }} />
              <button onClick={async () => { await api.setMarkerLabels(exp.id, (labelText || exp.marker_labels.map(l=>l.label).join(",")).split(",").map(s => s.trim()).filter(Boolean)); refresh(); }}
                className="rounded-lg px-3 text-xs font-semibold" style={{ color: "var(--accent)", background: "color-mix(in srgb, var(--accent) 12%, transparent)" }}>Save</button>
            </div>
          </Field>
          <div>
            <h4 className="mb-1 text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Participants</h4>
            <div className="flex flex-wrap gap-2">
              {participants.map((p) => (
                <span key={p.id} className="rounded-full px-2.5 py-1 text-xs"
                  style={{ background: "color-mix(in srgb, var(--accent) 10%, transparent)", color: "var(--accent)" }}>{p.code}</span>
              ))}
            </div>
            <div className="mt-2 flex gap-2">
              <input className="flex-1 rounded-lg border px-2 py-1 text-xs" value={pcode}
                onChange={(e) => setPcode(e.target.value)} placeholder="New participant code (e.g. P04)"
                style={{ borderColor: "var(--glass-border)", background: "var(--glass-bg)", color: "var(--text)" }} />
              <button onClick={async () => { if (pcode.trim()) { await api.createParticipant(exp.id, pcode.trim()); setPcode(""); refresh(); } }}
                className="rounded-lg px-3 text-xs font-semibold" style={{ background: "var(--accent)", color: "#fff" }}>Add</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify** `cd hri_monitor/ui && npx tsc --noEmit` → clean.
- [ ] **Step 3: Commit**

```bash
git add hri_monitor/ui/src/components/exp/ManageTab.tsx
git commit -m "feat(ui): experiments manage tab"
```

---

### Task 3: Run tab (`components/exp/RunTab.tsx`)

**Files:** Create `hri_monitor/ui/src/components/exp/RunTab.tsx`

- [ ] **Step 1: Implement**

Create `hri_monitor/ui/src/components/exp/RunTab.tsx`:

```tsx
import { Eye, HeartPulse, Square, Thermometer, Waves } from "lucide-react";
import { useState } from "react";
import { api, type Experiment, type Participant, type ActiveStatus } from "../../lib/experiments";
import { useLiveData } from "../../lib/ws";
import { SignalChart } from "../SignalChart";
import { Field, Select } from "../DeviceCard";

function fmt(s: number) {
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export function RunTab({ exp, participants, active }: {
  exp: Experiment | null; participants: Participant[]; active: ActiveStatus;
}) {
  const { latest, series } = useLiveData();
  const [participantId, setParticipantId] = useState<number | null>(null);
  const [conditionId, setConditionId] = useState<number | null>(null);
  const [text, setText] = useState("");
  const temps = latest["thermal.temps"];
  const recId = active?.recording_id ?? null;

  const start = async () => {
    if (exp && participantId && conditionId)
      await api.start({ experiment_id: exp.id, participant_id: participantId, condition_id: conditionId });
  };

  return (
    <div className="space-y-4">
      <div className="glass p-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <Field label="Participant">
            <Select value={participantId ?? ""} onChange={(e) => setParticipantId(Number(e.target.value))}>
              <option value="">— select —</option>
              {participants.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
            </Select>
          </Field>
          <Field label="Condition">
            <div className="flex flex-wrap gap-2">
              {exp?.conditions.map((c) => (
                <button key={c.id} onClick={() => setConditionId(c.id)}
                  className="rounded-full px-3 py-1 text-xs font-semibold"
                  style={conditionId === c.id
                    ? { background: "color-mix(in srgb, var(--accent) 18%, transparent)", color: "var(--accent)", border: "1px solid var(--accent)" }
                    : { color: "var(--text-muted)", border: "1px solid var(--glass-border)" }}>{c.name}</button>
              ))}
            </div>
          </Field>
        </div>
      </div>

      {active ? (
        <div className="glass flex items-center justify-between p-4">
          <div className="flex items-center gap-3">
            <span className="h-2.5 w-2.5 rounded-full motion-safe:animate-[pulse-dot_1.4s_infinite]"
              style={{ background: "var(--err)", boxShadow: "0 0 10px var(--err)" }} />
            <div>
              <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                Recording · {active.condition}
              </div>
              <div className="tnum text-2xl font-bold">{fmt(active.elapsed)}
                <span className="ml-2 text-sm" style={{ color: "var(--text-muted)" }}>· {active.sample_count} samples</span>
              </div>
            </div>
          </div>
          <button onClick={() => recId && api.stop(recId)}
            className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-bold"
            style={{ background: "var(--err)", color: "#0b1220" }}><Square size={14} /> Stop</button>
        </div>
      ) : (
        <button onClick={start} disabled={!exp || !participantId || !conditionId}
          className="glass w-full p-3 text-sm font-bold disabled:opacity-50"
          style={{ color: "var(--ok)" }}>● Start recording</button>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SignalChart title="GSR" unit="µS" colorVar="--chart-gsr" icon={Waves}
          points={series["shimmer.gsr"] ?? []} value={latest["shimmer.gsr"]?.value} />
        <SignalChart title="HR" unit="bpm" colorVar="--chart-ppg" icon={HeartPulse} glow={false}
          points={series["ppg.hr"] ?? []} value={latest["ppg.hr"]?.value} />
        <SignalChart title="Blink" unit="/min" colorVar="--chart-blink" icon={Eye}
          points={series["rgb.blink"] ?? []} value={latest["rgb.blink"]?.rate} />
        <SignalChart title="Forehead" unit="°C" colorVar="--chart-temp" icon={Thermometer}
          points={series["thermal.temps"] ?? []} value={temps?.forehead} />
      </div>

      <div className="glass p-4">
        <div className="mb-2 text-[10px] uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Markers</div>
        <div className="mb-2 flex flex-wrap gap-2">
          {exp?.marker_labels.map((l) => (
            <button key={l.id} disabled={!recId} onClick={() => recId && api.marker(recId, l.label, "button")}
              className="rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-40"
              style={{ background: "color-mix(in srgb, var(--accent) 12%, transparent)", color: "var(--accent)" }}>{l.label}</button>
          ))}
        </div>
        <div className="flex gap-2">
          <input className="flex-1 rounded-lg border px-2 py-1 text-xs" value={text} disabled={!recId}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && recId && text.trim()) { api.marker(recId, text.trim(), "text"); setText(""); } }}
            placeholder="Custom marker + Enter"
            style={{ borderColor: "var(--glass-border)", background: "var(--glass-bg)", color: "var(--text)" }} />
        </div>
        {active && active.markers.length > 0 && (
          <table className="mt-3 w-full text-xs">
            <tbody>
              {active.markers.map((m) => (
                <tr key={m.id}>
                  <td className="tnum py-1" style={{ color: "var(--text-muted)" }}>{fmt(m.t_offset)}</td>
                  <td>{m.label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify** `cd hri_monitor/ui && npx tsc --noEmit` → clean.
- [ ] **Step 3: Commit**

```bash
git add hri_monitor/ui/src/components/exp/RunTab.tsx
git commit -m "feat(ui): experiments run console"
```

---

### Task 4: Browse tab (`components/exp/BrowseTab.tsx`)

**Files:** Create `hri_monitor/ui/src/components/exp/BrowseTab.tsx`

- [ ] **Step 1: Implement**

Create `hri_monitor/ui/src/components/exp/BrowseTab.tsx`:

```tsx
import { Download } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Experiment, type Session, type Participant } from "../../lib/experiments";

function dur(s: Session["recordings"][number]) {
  if (!s.stopped_at) return "—";
  return `${Math.round(s.stopped_at - s.started_at)}s`;
}

export function BrowseTab({ exp, participants }: { exp: Experiment | null; participants: Participant[] }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  useEffect(() => { if (exp) api.listSessions(exp.id).then(setSessions); else setSessions([]); }, [exp]);
  const code = (pid: number) => participants.find((p) => p.id === pid)?.code ?? `#${pid}`;
  const condName = (cid: number) => exp?.conditions.find((c) => c.id === cid)?.name ?? "";

  if (!exp) return <p className="text-sm" style={{ color: "var(--text-muted)" }}>Select an experiment.</p>;
  return (
    <div className="space-y-4">
      {sessions.length === 0 && <p className="text-sm" style={{ color: "var(--text-muted)" }}>No sessions recorded yet.</p>}
      {sessions.map((s) => (
        <div key={s.id} className="glass p-4">
          <div className="mb-2 flex items-center justify-between">
            <b className="text-sm" style={{ color: "var(--text)" }}>{code(s.participant_id)} · session #{s.id}</b>
            <a href={`/api/sessions/${s.id}/export.zip`}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold"
              style={{ background: "color-mix(in srgb, var(--accent) 12%, transparent)", color: "var(--accent)" }}>
              <Download size={13} /> Session .zip
            </a>
          </div>
          <table className="w-full text-xs">
            <thead><tr style={{ color: "var(--text-muted)" }}>
              <th className="py-1 text-left">Condition</th><th className="text-left">Duration</th>
              <th className="text-left">Samples</th><th className="text-left">Markers</th><th></th></tr></thead>
            <tbody>
              {s.recordings.map((r) => (
                <tr key={r.id} style={{ borderTop: "1px solid var(--glass-border)" }}>
                  <td className="py-1.5" style={{ color: "var(--accent)" }}>{condName(r.condition_id)}</td>
                  <td className="tnum">{dur(r)}</td>
                  <td className="tnum">{r.sample_count}</td>
                  <td className="tnum">{r.marker_count ?? 0}</td>
                  <td><a href={`/api/recordings/${r.id}/export.csv`}
                    className="rounded-md px-2 py-0.5 text-[11px] font-semibold"
                    style={{ color: "var(--accent)" }}>⬇ CSV</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Verify** `cd hri_monitor/ui && npx tsc --noEmit` → clean.
- [ ] **Step 3: Commit**

```bash
git add hri_monitor/ui/src/components/exp/BrowseTab.tsx
git commit -m "feat(ui): experiments browse + export tab"
```

---

### Task 5: Experiments page + nav wiring

**Files:**
- Create: `hri_monitor/ui/src/pages/Experiments.tsx`
- Modify: `hri_monitor/ui/src/App.tsx`

- [ ] **Step 1: Implement the page**

Create `hri_monitor/ui/src/pages/Experiments.tsx`:

```tsx
import { useState } from "react";
import { ManageTab } from "../components/exp/ManageTab";
import { RunTab } from "../components/exp/RunTab";
import { BrowseTab } from "../components/exp/BrowseTab";
import { useActiveRecording, useExperiment, useExperiments } from "../lib/experiments";

const TABS = ["Manage", "Run", "Browse"] as const;
type Tab = (typeof TABS)[number];

export function Experiments() {
  const [tab, setTab] = useState<Tab>("Manage");
  const [selected, setSelected] = useState<number | null>(null);
  const { experiments, refresh: refreshList } = useExperiments();
  const { exp, participants, refresh } = useExperiment(selected);
  const active = useActiveRecording();

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className="rounded-lg px-4 py-2 text-sm font-semibold"
            style={tab === t
              ? { background: "color-mix(in srgb, var(--accent) 15%, transparent)", color: "var(--accent)" }
              : { color: "var(--text-muted)" }}>{t}</button>
        ))}
        {active && <span className="ml-auto self-center text-xs" style={{ color: "var(--err)" }}>● recording</span>}
      </div>
      {tab === "Manage" && (
        <ManageTab experiments={experiments} selected={selected} onSelect={setSelected}
          exp={exp} participants={participants} refresh={refresh} refreshList={refreshList} />
      )}
      {tab === "Run" && <RunTab exp={exp} participants={participants} active={active} />}
      {tab === "Browse" && <BrowseTab exp={exp} participants={participants} />}
    </div>
  );
}
```

- [ ] **Step 2: Wire into `App.tsx`**

Add the import near the other page imports:
```tsx
import { Experiments } from "./pages/Experiments";
```
In the `<main>` render chain, add an Experiments branch (before the placeholder fallback):
```tsx
        ) : page === "Experiments" ? (
          <Experiments />
```
So the chain reads `page === "Live" ? <Live/> : page === "Devices" ? <Devices/> : page === "Experiments" ? <Experiments/> : (placeholder)`.

- [ ] **Step 3: Verify** `cd hri_monitor/ui && npx tsc --noEmit && npm run build && test -f ../ui_dist/index.html && echo BUILD_OK` → BUILD_OK.

- [ ] **Step 4: Commit (source only)**

```bash
git add hri_monitor/ui/src/pages/Experiments.tsx hri_monitor/ui/src/App.tsx
git commit -m "feat(ui): experiments page wired into nav"
```

---

### Task 6: Live verification + rebuild ui_dist

**Files:** Commit `hri_monitor/ui_dist/`

- [ ] **Step 1: Rebuild + font check**

Run: `cd hri_monitor/ui && npm run build && (grep -rqE "fonts.googleapis|gstatic" ../ui_dist/ && echo CDN || echo NO_CDN)`
Expected: `NO_CDN`.

- [ ] **Step 2: Live end-to-end against the backend (simulators)**

```bash
cd hri_monitor && .venv/bin/python run.py --no-browser & sleep 4
curl -s http://127.0.0.1:8000/ | grep -o "<title>HRI Monitor</title>"
# full flow via the same API the UI uses
EXP=$(curl -s -X POST http://127.0.0.1:8000/api/experiments -H 'Content-Type: application/json' -d '{"name":"UI Smoke"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X PUT http://127.0.0.1:8000/api/experiments/$EXP/conditions -H 'Content-Type: application/json' -d '{"conditions":["Baseline","Task"]}' >/dev/null
COND=$(curl -s http://127.0.0.1:8000/api/experiments/$EXP | python3 -c "import sys,json;print(json.load(sys.stdin)['conditions'][0]['id'])")
PART=$(curl -s -X POST http://127.0.0.1:8000/api/experiments/$EXP/participants -H 'Content-Type: application/json' -d '{"code":"P01"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
REC=$(curl -s -X POST http://127.0.0.1:8000/api/recordings/start -H 'Content-Type: application/json' -d "{\"experiment_id\":$EXP,\"participant_id\":$PART,\"condition_id\":$COND}" | python3 -c "import sys,json;print(json.load(sys.stdin)['recording_id'])")
sleep 2; curl -s http://127.0.0.1:8000/api/recordings/active | python3 -c "import sys,json;d=json.load(sys.stdin);print('elapsed',d['elapsed'],'samples',d['sample_count'])"
curl -s -X POST http://127.0.0.1:8000/api/recordings/$REC/stop >/dev/null
curl -s "http://127.0.0.1:8000/api/sessions/$(curl -s http://127.0.0.1:8000/api/experiments/$EXP/sessions | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["id"])')/export.zip" -o /tmp/sess.zip
python3 -c "import zipfile;z=zipfile.ZipFile('/tmp/sess.zip');print('zip names:', z.namelist())"
kill %1; git checkout config.yaml 2>/dev/null || true
```
Expected: title served; active shows elapsed/samples climbing; zip contains `session.json`, `manifest.csv`, and a `recordings/*.csv`. For a visual check, run `python run.py`, open Experiments → Manage (create experiment + conditions + participant), Run (Start → markers → Stop), Browse (download CSV/zip).

- [ ] **Step 3: Python regression**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests -q`
Expected: all pass (unchanged from backend plan; UI doesn't touch Python).

- [ ] **Step 4: Commit rebuilt bundle**

```bash
git add hri_monitor/ui_dist
git commit -m "feat(ui): rebuild ui_dist with experiments page"
git status --short   # clean (data/ gitignored)
```

Report the Experiments milestone (data collection) complete.
