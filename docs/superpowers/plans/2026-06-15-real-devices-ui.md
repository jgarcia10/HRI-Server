# Milestone 2 UI — Devices Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Clinical Frost Devices page that lists the three devices, lets the user configure each (camera index, thermal XML, sampling rate, Real⇄Simulator), drive lifecycle (connect/disconnect/restart), and scan→pair→connect the Shimmer over Bluetooth — all hitting the milestone-2 backend API.

**Architecture:** A `useDevices()` hook polls `GET /api/devices` (~1 s) for config/status/options and posts config/lifecycle/bluetooth actions; live status also keeps flowing via the existing `/ws` `devices` field. A reusable `DeviceCard` renders any device; a `BluetoothScan` component handles the Shimmer scan/pair flow. Clinical Frost tokens + existing `StatusChip` only — no new design language.

**Tech Stack:** React 18, Vite 5, Tailwind v4, lucide-react. Verification: `npx tsc --noEmit` + `npm run build`, then live against the backend.

**Spec:** `docs/superpowers/specs/2026-06-15-hri-monitor-real-devices.md` §8.
**Prerequisite:** the backend plan (`2026-06-15-real-devices-backend.md`) is merged — the API endpoints exist.

**Working dir:** `hri_monitor/ui` for UI commands; `hri_monitor` for the live check. Do NOT commit `ui_dist` until the final task (it rebuilds each task).

---

### Task 1: `useDevices` hook + API client

**Files:**
- Create: `hri_monitor/ui/src/lib/devices.ts`

- [ ] **Step 1: Implement the hook + API helpers**

Create `hri_monitor/ui/src/lib/devices.ts`:

```ts
import { useCallback, useEffect, useRef, useState } from "react";

export type DeviceConfig = {
  simulate?: boolean;
  index?: number; width?: number; height?: number; fps?: number;
  xml?: string; mac?: string; sampling_rate?: number;
};
export type Camera = { index: number; path: string; name: string };
export type BtDevice = { mac: string; name: string; paired: boolean };
export type DevicesState = {
  devices: Record<string, { config: DeviceConfig; status: string }>;
  options: { cameras: Camera[]; sampling_rates: number[]; serial_ports: string[] };
};

const EMPTY: DevicesState = {
  devices: {},
  options: { cameras: [], sampling_rates: [], serial_ports: [] },
};

export function useDevices() {
  const [state, setState] = useState<DevicesState>(EMPTY);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const refresh = useCallback(async () => {
    try {
      const r = await fetch("/api/devices");
      if (r.ok) setState(await r.json());
    } catch {
      /* keep last state; backend may be momentarily busy */
    }
  }, []);

  useEffect(() => {
    let stopped = false;
    const loop = async () => {
      await refresh();
      if (!stopped) timer.current = setTimeout(loop, 1000);
    };
    loop();
    return () => {
      stopped = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [refresh]);

  const setConfig = useCallback(async (name: string, cfg: DeviceConfig) => {
    setBusy((b) => ({ ...b, [name]: true }));
    try {
      await fetch(`/api/devices/${name}/config`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cfg),
      });
      await refresh();
    } finally {
      setBusy((b) => ({ ...b, [name]: false }));
    }
  }, [refresh]);

  const action = useCallback(async (name: string, act: "restart" | "connect" | "disconnect") => {
    setBusy((b) => ({ ...b, [name]: true }));
    try {
      await fetch(`/api/devices/${name}/${act}`, { method: "POST" });
      await refresh();
    } finally {
      setBusy((b) => ({ ...b, [name]: false }));
    }
  }, [refresh]);

  return { state, busy, setConfig, action, refresh };
}

export async function btScan(seconds = 8): Promise<BtDevice[]> {
  const r = await fetch("/api/bluetooth/scan", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ seconds }),
  });
  return r.ok ? (await r.json()).devices : [];
}

export async function btPair(mac: string, pin = "1234"): Promise<{ ok: boolean; reason: string }> {
  const r = await fetch("/api/bluetooth/pair", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mac, pin }),
  });
  return r.json();
}
```

- [ ] **Step 2: Verify type-check**

Run: `cd hri_monitor/ui && npx tsc --noEmit`
Expected: clean (the hook isn't imported yet, but tsc checks `src/`).

- [ ] **Step 3: Commit**

```bash
git add hri_monitor/ui/src/lib/devices.ts
git commit -m "feat(ui): useDevices hook + device/bluetooth api client"
```

---

### Task 2: Shared `DeviceCard` + `Field` primitives

**Files:**
- Create: `hri_monitor/ui/src/components/DeviceCard.tsx`

- [ ] **Step 1: Implement DeviceCard**

Create `hri_monitor/ui/src/components/DeviceCard.tsx`:

```tsx
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { StatusChip } from "./StatusChip";

export function DeviceCard({
  name, icon: Icon, status, simulate, busy, onToggleSim, onRestart, onDisconnect, children,
}: {
  name: string;
  icon: LucideIcon;
  status: string;
  simulate: boolean;
  busy?: boolean;
  onToggleSim: (sim: boolean) => void;
  onRestart: () => void;
  onDisconnect: () => void;
  children: ReactNode;
}) {
  return (
    <div className="glass p-4">
      <div className="mb-3 flex items-center gap-2">
        <Icon size={16} style={{ color: "var(--accent)" }} />
        <b className="text-sm" style={{ color: "var(--text)" }}>{name}</b>
        <span className="ml-auto"><StatusChip name="" status={busy ? "connecting" : status} /></span>
      </div>
      <div className="space-y-2 text-sm">{children}</div>
      <div className="mt-3 flex items-center gap-2">
        <button onClick={onRestart} disabled={busy}
          className="rounded-lg px-3 py-1.5 text-xs font-semibold"
          style={{ color: "var(--accent)", background: "color-mix(in srgb, var(--accent) 12%, transparent)" }}>
          Restart
        </button>
        <button onClick={onDisconnect} disabled={busy}
          className="rounded-lg border px-3 py-1.5 text-xs"
          style={{ color: "var(--text-muted)", borderColor: "var(--glass-border)" }}>
          Disconnect
        </button>
        <label className="ml-auto flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
          {simulate ? "Simulator" : "Real"}
          <input type="checkbox" checked={!simulate} onChange={(e) => onToggleSim(!e.target.checked)} />
        </label>
      </div>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 shrink-0 text-xs" style={{ color: "var(--text-muted)" }}>{label}</span>
      <div className="flex-1">{children}</div>
    </div>
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props}
      className="w-full rounded-lg border px-2 py-1 text-xs"
      style={{ borderColor: "var(--glass-border)", background: "var(--glass-bg)", color: "var(--text)" }} />
  );
}
```

- [ ] **Step 2: Verify**

Run: `cd hri_monitor/ui && npx tsc --noEmit`
Expected: clean. (`StatusChip` renders `name · status`; passing `name=""` yields a leading "· status" — acceptable for the chip-as-status-badge use; if it reads oddly the Devices page can pass the device name. Keep `name=""` here so the header isn't doubled.)

- [ ] **Step 3: Commit**

```bash
git add hri_monitor/ui/src/components/DeviceCard.tsx
git commit -m "feat(ui): reusable device card + field primitives"
```

---

### Task 3: `BluetoothScan` component

**Files:**
- Create: `hri_monitor/ui/src/components/BluetoothScan.tsx`

- [ ] **Step 1: Implement**

Create `hri_monitor/ui/src/components/BluetoothScan.tsx`:

```tsx
import { Bluetooth, Loader2 } from "lucide-react";
import { useState } from "react";
import { btPair, btScan, type BtDevice } from "../lib/devices";

export function BluetoothScan({ onPaired }: { onPaired: (mac: string) => void }) {
  const [scanning, setScanning] = useState(false);
  const [devices, setDevices] = useState<BtDevice[]>([]);
  const [pairing, setPairing] = useState<string | null>(null);
  const [msg, setMsg] = useState<string>("");

  const scan = async () => {
    setScanning(true);
    setMsg("");
    try {
      setDevices(await btScan(8));
    } finally {
      setScanning(false);
    }
  };

  const pair = async (mac: string) => {
    setPairing(mac);
    setMsg("");
    try {
      const r = await btPair(mac);
      if (r.ok) onPaired(mac);
      else setMsg(r.reason || "pairing failed");
    } finally {
      setPairing(null);
    }
  };

  return (
    <div className="rounded-xl border border-dashed p-2"
      style={{ borderColor: "var(--accent)", background: "color-mix(in srgb, var(--accent) 4%, transparent)" }}>
      <div className="flex items-center gap-2 text-xs" style={{ color: "var(--accent)" }}>
        <Bluetooth size={13} /> Bluetooth
        <button onClick={scan} disabled={scanning}
          className="ml-auto rounded-md px-2 py-1 font-semibold"
          style={{ background: "var(--accent)", color: "#fff" }}>
          {scanning ? "Scanning…" : "Scan"}
        </button>
      </div>
      {devices.map((d) => (
        <div key={d.mac} className="mt-1 flex items-center gap-2 rounded-md px-1 py-1 text-xs"
          style={{ color: "var(--text)" }}>
          <span>{d.paired ? "🔵" : "⚪"}</span>
          <span>{d.name}</span>
          <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>{d.mac}</span>
          <button onClick={() => pair(d.mac)} disabled={pairing === d.mac}
            className="ml-auto rounded-md px-2 py-0.5 font-semibold"
            style={{ color: "var(--accent)", background: "color-mix(in srgb, var(--accent) 12%, transparent)" }}>
            {pairing === d.mac ? <Loader2 size={12} className="animate-spin" /> : d.paired ? "Use" : "Pair"}
          </button>
        </div>
      ))}
      {devices.length > 0 && (
        <div className="mt-1 text-[10px]" style={{ color: "var(--text-muted)" }}>
          If prompted, the Shimmer PIN is <b>1234</b>.
        </div>
      )}
      {msg && <div className="mt-1 text-[10px]" style={{ color: "var(--err)" }}>{msg}</div>}
    </div>
  );
}
```

- [ ] **Step 2: Verify**

Run: `cd hri_monitor/ui && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add hri_monitor/ui/src/components/BluetoothScan.tsx
git commit -m "feat(ui): bluetooth scan/pair component"
```

---

### Task 4: Devices page + wire into App nav

**Files:**
- Create: `hri_monitor/ui/src/pages/Devices.tsx`
- Modify: `hri_monitor/ui/src/App.tsx`

- [ ] **Step 1: Implement the Devices page**

Create `hri_monitor/ui/src/pages/Devices.tsx`:

```tsx
import { Cpu, Thermometer, Waves } from "lucide-react";
import { DeviceCard, Field, Select } from "../components/DeviceCard";
import { BluetoothScan } from "../components/BluetoothScan";
import { useDevices } from "../lib/devices";

const THERMAL_XMLS = ["15030138.xml", "16070070.xml", "first_camera.xml"];

export function Devices() {
  const { state, busy, setConfig, action } = useDevices();
  const d = state.devices;
  const rgb = d.rgb?.config ?? {};
  const thermal = d.thermal?.config ?? {};
  const shimmer = d.shimmer?.config ?? {};

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {/* Thermal */}
      <DeviceCard name="Thermal (Optris)" icon={Thermometer}
        status={d.thermal?.status ?? "disabled"} simulate={thermal.simulate ?? true} busy={busy.thermal}
        onToggleSim={(sim) => setConfig("thermal", { simulate: sim })}
        onRestart={() => action("thermal", "restart")} onDisconnect={() => action("thermal", "disconnect")}>
        <Field label="Calibration">
          <Select value={thermal.xml ?? ""} onChange={(e) => setConfig("thermal", { xml: e.target.value })}>
            {THERMAL_XMLS.map((x) => <option key={x} value={x}>{x}</option>)}
          </Select>
        </Field>
        <Field label="Detector"><span className="text-xs" style={{ color: "var(--text-muted)" }}>dlib (thermal-trained)</span></Field>
      </DeviceCard>

      {/* RGB */}
      <DeviceCard name="RGB camera" icon={Cpu}
        status={d.rgb?.status ?? "disabled"} simulate={rgb.simulate ?? true} busy={busy.rgb}
        onToggleSim={(sim) => setConfig("rgb", { simulate: sim })}
        onRestart={() => action("rgb", "restart")} onDisconnect={() => action("rgb", "disconnect")}>
        <Field label="Device">
          <Select value={rgb.index ?? 0} onChange={(e) => setConfig("rgb", { index: Number(e.target.value) })}>
            {state.options.cameras.length === 0 && <option value={rgb.index ?? 0}>/dev/video{rgb.index ?? 0}</option>}
            {state.options.cameras.map((c) => (
              <option key={c.index} value={c.index}>{c.path} — {c.name}</option>
            ))}
          </Select>
        </Field>
        <Field label="Resolution">
          <Select value={`${rgb.width}x${rgb.height}`}
            onChange={(e) => { const [w, h] = e.target.value.split("x").map(Number); setConfig("rgb", { width: w, height: h }); }}>
            <option value="640x480">640×480</option>
            <option value="1280x720">1280×720</option>
          </Select>
        </Field>
      </DeviceCard>

      {/* Shimmer */}
      <DeviceCard name="Shimmer GSR" icon={Waves}
        status={d.shimmer?.status ?? "disabled"} simulate={shimmer.simulate ?? true} busy={busy.shimmer}
        onToggleSim={(sim) => setConfig("shimmer", { simulate: sim })}
        onRestart={() => action("shimmer", "restart")} onDisconnect={() => action("shimmer", "disconnect")}>
        <Field label="Device"><span className="text-xs" style={{ color: "var(--text)" }}>{shimmer.mac ?? "— not paired —"}</span></Field>
        <Field label="Sampling">
          <Select value={shimmer.sampling_rate ?? 200} onChange={(e) => setConfig("shimmer", { sampling_rate: Number(e.target.value) })}>
            {(state.options.sampling_rates.length ? state.options.sampling_rates : [128, 200, 256, 512]).map((r) => (
              <option key={r} value={r}>{r} Hz</option>
            ))}
          </Select>
        </Field>
        <BluetoothScan onPaired={(mac) => setConfig("shimmer", { mac, simulate: false })} />
      </DeviceCard>
    </div>
  );
}
```

- [ ] **Step 2: Wire into App nav** — in `hri_monitor/ui/src/App.tsx`, import the page and render it for the "Devices" route. Add the import near the other page import:

```tsx
import { Devices } from "./pages/Devices";
```

Then change the main-area render so Devices is no longer a placeholder. Replace the `<main>` body:

```tsx
      <main className="min-w-0 flex-1 p-6">
        {page === "Live" ? (
          <Live />
        ) : page === "Devices" ? (
          <Devices />
        ) : (
          <div className="glass flex h-40 items-center justify-center text-sm" style={{ color: "var(--text-muted)" }}>
            “{page}” arrives in a later milestone — already dressed in Clinical Frost.
          </div>
        )}
      </main>
```

- [ ] **Step 3: Verify**

Run: `cd hri_monitor/ui && npx tsc --noEmit && npm run build && test -f ../ui_dist/index.html && echo BUILD_OK`
Expected: `BUILD_OK`.

- [ ] **Step 4: Commit (source only; ui_dist committed in Task 5)**

```bash
git add hri_monitor/ui/src/pages/Devices.tsx hri_monitor/ui/src/App.tsx
git commit -m "feat(ui): devices page wired into nav"
```

---

### Task 5: Live verification + rebuild ui_dist + commit

**Files:**
- Commit: `hri_monitor/ui_dist/`

- [ ] **Step 1: Rebuild**

Run: `cd hri_monitor/ui && npm run build && grep -rE "fonts.googleapis|gstatic" ../ui_dist/ || echo NO_CDN`
Expected: `NO_CDN`.

- [ ] **Step 2: Live check against the backend (simulator mode — no hardware needed)**

```bash
cd hri_monitor && .venv/bin/python run.py --no-browser & sleep 4
curl -s http://127.0.0.1:8000/api/devices | grep -c '"status"'
curl -s -X POST http://127.0.0.1:8000/api/devices/rgb/config -H "Content-Type: application/json" -d '{"simulate": true, "index": 0}' | head -c 120
curl -s http://127.0.0.1:8000/ | grep -o "<title>HRI Monitor</title>"
kill %1
```

Expected: device count ≥ 1; config POST returns `{"ok":true,...}`; title present. Then open `python run.py` and confirm visually: Devices page shows three cards, the RGB device dropdown lists real `/dev/videoN` cameras, the theme still toggles, status chips update. (Hardware connection itself is exercised in the manual-smoke task once you flip a device to Real.)

- [ ] **Step 3: Python regression**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests -q`
Expected: all pass (unchanged from backend plan; UI doesn't touch Python).

- [ ] **Step 4: Commit the rebuilt bundle**

```bash
git add hri_monitor/ui_dist
git commit -m "feat(ui): rebuild ui_dist with devices page"
git status --short
```

Expected: clean.

---

### Task 6: Manual hardware smoke (documented checklist — run on the rig)

**Files:** none (manual verification on real hardware; install deps first).

- [ ] **Step 1: Install hardware deps on the lab machine**

Run: `cd hri_monitor && .venv/bin/pip install -r requirements.txt`
Expected: `mediapipe`, `dlib`, `pyserial` install (dlib builds; needs cmake + a C++ toolchain). Report any build failure.

- [ ] **Step 2: RGB**

Launch `python run.py`, open Devices, flip RGB to **Real**, pick the USB webcam from the dropdown. Expected: status → connected; Live page RGB feed shows the webcam with eye landmarks + blink rate; blink chart moves.

- [ ] **Step 3: Thermal**

Flip Thermal to **Real**, pick the calibration XML matching your camera serial. Expected: status → connected within a few seconds (worker spawns, SDK inits); Live thermal feed shows the palette image with ROI boxes; the four facial-temperature values populate. If it stays "reconnecting", check the device's reason text and the hub log for the worker's stderr.

- [ ] **Step 4: Shimmer**

Power on the Shimmer. On the Shimmer card click **Scan**, find `Shimmer3-xxxx`, click **Pair** (enter PIN 1234 if prompted on the OS), then it auto-connects (mac saved, simulate off). Expected: status → connected; GSR/PPG charts move; HR appears after a few seconds of PPG.

- [ ] **Step 5: Persistence + hot-reconfigure**

Change the RGB camera index, confirm it restarts just that feed live. Restart `python run.py` and confirm the device choices (Real + indices + Shimmer MAC) persisted via `config.yaml`.

- [ ] **Step 6: Report**

Report which devices connected, any reason strings for failures, and confirm the simulator toggle still falls back per device. This closes milestone 2.
