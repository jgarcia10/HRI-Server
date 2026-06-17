import { useEffect, useRef, useState } from "react";

export type Point = { t: number; v: number };
export type LiveState = {
  latest: Record<string, any>;
  series: Record<string, Point[]>;
  devices: Record<string, string>;
  connected: boolean;
};

// Topics drawn as time series, and how to pull a number out of each payload.
const SERIES_EXTRACTORS: Record<string, (d: any) => number> = {
  "shimmer.gsr": (d) => d.value,
  "shimmer.ppg": (d) => d.value,
  "ppg.hr": (d) => d.value,
  "ppg.hrv": (d) => d.value,
  "rgb.blink": (d) => d.rate,
  "thermal.temps": (d) => d.forehead,
};
const MAX_POINTS = 300;

export function useLiveData(): LiveState {
  const [state, setState] = useState<LiveState>({
    latest: {},
    series: {},
    devices: {},
    connected: false,
  });
  const retry = useRef(1000);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

    function connect() {
      if (closed) return;
      ws = new WebSocket(`ws://${location.host}/ws`);
      ws.onopen = () => {
        retry.current = 1000;
        setState((s) => ({ ...s, connected: true }));
      };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "hello") {
          setState((s) => ({ ...s, devices: msg.devices }));
        } else if (msg.type === "update") {
          setState((s) => {
            const latest = { ...s.latest };
            const series = { ...s.series };
            for (const [topic, sample] of Object.entries<any>(msg.items)) {
              latest[topic] = sample.data;
              const extract = SERIES_EXTRACTORS[topic];
              if (extract) {
                const prev = series[topic] ?? [];
                series[topic] = [...prev.slice(-MAX_POINTS + 1), { t: sample.ts, v: extract(sample.data) }];
              }
            }
            return { ...s, latest, series, devices: msg.devices ?? s.devices };
          });
        }
      };
      ws.onclose = () => {
        setState((s) => ({ ...s, connected: false }));
        if (!closed) {
          reconnectTimer = setTimeout(connect, retry.current);
          retry.current = Math.min(retry.current * 2, 10000);
        }
      };
    }

    connect();
    return () => {
      closed = true;
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, []);

  return state;
}
