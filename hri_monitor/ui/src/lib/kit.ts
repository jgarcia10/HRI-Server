import { useEffect, useRef, useState } from "react";

export type KitPart = { id: string; type: string; color: string; depot_slot: string };
export type KitTaskState = {
  phase: "idle" | "running" | "between_orders" | "done";
  order_index: number;
  order_id: string | null;
  kind: string | null;
  step_index: number;
  n_parts: number;
  current_part: KitPart | null;
  remaining_s: number | null;
  queue: string[];
  perturbation_applied: boolean;
};

export function useKitWs() {
  const [task, setTask] = useState<KitTaskState | null>(null);
  const [connected, setConnected] = useState(false);
  const retry = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => setConnected(true);
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "update" && msg.items?.["task.state"]) {
          setTask(msg.items["task.state"].data as KitTaskState);
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry.current = setTimeout(connect, 1000);
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry.current);
      ws?.close();
    };
  }, []);
  return { task, connected };
}

const post = (url: string, body?: unknown) =>
  fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then(async (r) => {
    if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? r.statusText);
    return r.json();
  });

export const startSession = (body: { participant_code: string; condition: string; block?: string }) =>
  post("/api/kit/session/start", body);
export const stopSession = () => post("/api/kit/session/stop");
export const postEvent = (type: string, payload: Record<string, unknown> = {}) =>
  post("/api/kit/event", { type, payload });
