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

export type RobotState = {
  connected: boolean;
  backend: string;
  busy: boolean;
  gripper_closed: boolean;
  pace: string;
  last_skill: string | null;
  safety: string;
  queue: number;
};

export type SupplyState = {
  profile: {
    lookahead: number;
    side: string;
    pace: string;
    announce: boolean;
  };
  order_id: string | null;
  staged: Record<string, string>;
  inflight: string[];
  supplied: string[];
  next_part_id: string | null;
  failed: string[];
  blocked: { reason: string; needed: string | null; [k: string]: unknown } | null;
};

export function useKitWs() {
  const [task, setTask] = useState<KitTaskState | null>(null);
  const [robot, setRobot] = useState<RobotState | null>(null);
  const [supply, setSupply] = useState<SupplyState | null>(null);
  const [connected, setConnected] = useState(false);
  const retry = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    // Seed initial state on mount/remount (page reload, tab switch): the WS only
    // delivers task.state on the next change, so without this a reconnecting UI
    // sits at task === null until something happens. Subsequent WS updates take over.
    fetch("/api/kit/state")
      .then((r) => r.json())
      .then((d) => {
        const t = d?.session?.task;
        if (t) setTask(t as KitTaskState);
      })
      .catch(() => {});
    fetch("/api/kit/robot/state")
      .then((r) => r.json())
      .then((d) => {
        if (d) setRobot(d as RobotState);
      })
      .catch(() => {});
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => setConnected(true);
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "update") {
          if (msg.items?.["task.state"]) {
            setTask(msg.items["task.state"].data as KitTaskState);
          }
          if (msg.items?.["robot.state"]) {
            setRobot(msg.items["robot.state"].data as RobotState);
          }
          if (msg.items?.["supply.state"]) {
            setSupply(msg.items["supply.state"].data as SupplyState);
          }
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
  return { task, robot, supply, connected };
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

export const robotHome = () => post("/api/kit/robot/home");
export const robotStop = () => post("/api/kit/robot/stop");
export const robotOpenGripper = () => post("/api/kit/robot/open_gripper");
export const setSupplyProfile = (p: Partial<SupplyState["profile"]>) =>
  post("/api/kit/supply/profile", p);
export const startSession = (body: {
  participant_code: string;
  condition: string;
  block?: string;
  profile?: Partial<SupplyState["profile"]>;
}) => post("/api/kit/session/start", body);
export const stopSession = () => post("/api/kit/session/stop");
export const postEvent = (type: string, payload: Record<string, unknown> = {}) =>
  post("/api/kit/event", { type, payload });
