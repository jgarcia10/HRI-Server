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
