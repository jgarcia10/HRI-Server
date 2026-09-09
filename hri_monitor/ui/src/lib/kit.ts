import { useEffect, useRef, useState } from "react";

export type KitPart = {
  id: string;
  type: "1x2" | "1x1" | "slope" | string;
  color: "red" | "orange" | "blue" | "seafoam" | "lime" | string;
  depot_slot: string;
  pos: [number, number]; // x in studs from the left, layer from the table
  high: "left" | "right" | null; // slopes: side of the tall edge
  width: number; // studs
};
export type KitTaskState = {
  phase: "idle" | "running" | "between_orders" | "done";
  order_index: number;
  order_id: string | null;
  order_name: string | null;
  kind: string | null;
  parts: KitPart[]; // assembly sequence (index = step), with placement geometry
  width_studs: number;
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
  latched: "estop" | "protective_stop" | "emergency_stop" | "robot_fault" | null;
};

export type SupplyState = {
  profile: {
    lookahead: number;
    side: string;
    pace: string;
    announce: boolean;
  };
  order_id: string | null;
  paused: boolean;
  staged: Record<string, string>;
  inflight: string[];
  supplied: string[];
  next_part_id: string | null;
  failed: string[];
  blocked: {
    reason:
      | "mat_full"
      | "part_failed"
      | "estop"
      | "protective_stop"
      | "emergency_stop"
      | "robot_fault";
    needed: string | null;
    [k: string]: unknown;
  } | null;
};

export type QuestionnaireItem = {
  key: string;
  label: string;
  question: string;
  low: string;
  high: string;
};
export type Instrument = {
  title: string;
  scale: { min: number; max: number; step: number };
  score: string;
  items: QuestionnaireItem[];
};
export type QuestionnaireState =
  | { status: "none" }
  | {
      status: "pending";
      session_id: number;
      participant: string;
      condition: string;
      block: string | null;
      done: Record<string, number>;
      next: "nasa_tlx" | "trust_hrts" | null;
      instruments: Record<string, Instrument>;
      order: string[];
    }
  | {
      status: "done";
      participant: string;
      condition: string;
      session_id: number;
      done: Record<string, number>;
      outcome: "completed" | "skipped";
    };

export function useKitWs() {
  const [task, setTask] = useState<KitTaskState | null>(null);
  const [robot, setRobot] = useState<RobotState | null>(null);
  const [supply, setSupply] = useState<SupplyState | null>(null);
  const [questionnaire, setQuestionnaire] = useState<QuestionnaireState>({ status: "none" });
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
    // supply.state is only streamed on change: a wizard page opened mid-session would show
    // empty staging slots until the next robot event without this seed.
    fetch("/api/kit/supply/state")
      .then((r) => r.json())
      .then((d) => {
        if (d && d.profile) setSupply(d as SupplyState);
      })
      .catch(() => {});
    fetch("/api/kit/questionnaire")
      .then((r) => r.json())
      .then((d) => {
        if (d && d.status) setQuestionnaire(d as QuestionnaireState);
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
          if (msg.items?.["kit.questionnaire"]) {
            setQuestionnaire(msg.items["kit.questionnaire"].data as QuestionnaireState);
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
  return { task, robot, supply, questionnaire, connected };
}

export const submitQuestionnaire = (instrument: string, answers: Record<string, number>) =>
  post("/api/kit/questionnaire", { instrument, answers });
export const skipQuestionnaires = (reason?: string) =>
  post("/api/kit/questionnaire/skip", { reason: reason ?? null });

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
export const robotConnect = () => post("/api/kit/robot/connect");
export const setSupplyProfile = (p: Partial<SupplyState["profile"]>) =>
  post("/api/kit/supply/profile", p);
export const startSession = (body: {
  participant_code: string;
  condition: string;
  block?: string;
  profile?: Partial<SupplyState["profile"]>;
}) => post("/api/kit/session/start", body);
export const stopSession = () => post("/api/kit/session/stop");
export type PlanBlock = { block: 1 | 2; condition: "C0" | "C1"; family: "F1" | "F2"; orders: string };
export type Plan = { participant: string; number: number | null; group: number; blocks: PlanBlock[]; label: string };
export const fetchPlan = (participant: string): Promise<Plan> =>
  fetch(`/api/kit/plan/${encodeURIComponent(participant)}`).then((r) => r.json());
export const postEvent = (type: string, payload: Record<string, unknown> = {}) =>
  post("/api/kit/event", { type, payload });
export const matCleared = () => postEvent("mat_cleared");
