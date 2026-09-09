/**
 * Plain-language vocabulary for the experimenter page.
 *
 * The hub speaks in study codes (C0/C1, F1/F2, `F1O1P1`, `lookahead`, `protective_stop`).
 * The person running the session should never have to decode those mid-experiment, so every
 * label the eye lands on is a normal English phrase and the code, when it still matters for
 * the logbook, rides along as small secondary text. Nothing here touches the wire format:
 * the API payloads keep using the codes.
 */
import type { KitPart, KitTaskState } from "../../lib/kit";

/** Colour role shared by every status surface on the page. */
export type Tone = "ok" | "warn" | "err" | "muted" | "accent";

/* ------------------------------------------------------------------ pieces */

/** Brick colours as seen on the table (the same swatch the participant is holding). */
export const PART_COLORS: Record<string, string> = {
  red: "#d64541",
  orange: "#e67e22",
  blue: "#2e86de",
  seafoam: "#7fd6c2",
  lime: "#a3cb38",
};

export const colorHex = (color: string | undefined): string =>
  (color && PART_COLORS[color]) || "#94a3b8";

/** Colour words an experimenter would actually say out loud. */
const COLOR_WORD: Record<string, string> = {
  red: "red",
  orange: "orange",
  blue: "blue",
  seafoam: "mint",
  lime: "lime",
};

/** Brick types → shapes, not stud dimensions. */
const SHAPE_WORD: Record<string, string> = {
  "1x2": "long brick",
  "1x1": "small brick",
  slope: "roof piece",
};

export const shapeWord = (type: string | undefined): string =>
  (type && SHAPE_WORD[type]) || type || "piece";

export const colorWord = (color: string | undefined): string =>
  (color && COLOR_WORD[color]) || color || "";

/** "red long brick" — never `F1O1P1`. */
export function partName(part: KitPart | null | undefined): string {
  if (!part) return "—";
  return `${colorWord(part.color)} ${shapeWord(part.type)}`.trim();
}

/** Resolve a part id coming from supply state against the current figure's part list. */
export function findPart(task: KitTaskState | null, id: string | null | undefined): KitPart | null {
  if (!task || !id) return null;
  return task.parts?.find((p) => p.id === id) ?? null;
}

/* -------------------------------------------------------------------- mat */

export type Slot = "L" | "C" | "R";
export const SLOTS: Slot[] = ["L", "C", "R"];
export const SLOT_WORD: Record<string, string> = { L: "Left", C: "Center", R: "Right" };
export const slotWord = (slot: string | undefined): string =>
  (slot && SLOT_WORD[slot]) || slot || "—";

/* --------------------------------------------------------- study conditions */

export type ConditionCode = "C0" | "C1";
export const CONDITIONS: {
  code: ConditionCode;
  name: string;
  detail: string;
  blurb: string;
}[] = [
  {
    code: "C0",
    name: "Baseline",
    detail: "C0 · LLM + RLHF",
    blurb: "Fixed assistant, keeps the whole block in context",
  },
  {
    code: "C1",
    name: "Adaptive",
    detail: "C1 · homeostatic/allostatic meta-RL",
    blurb: "Assistant adapts to the participant during the block",
  },
];
export const conditionInfo = (code: string) =>
  CONDITIONS.find((c) => c.code === code) ?? CONDITIONS[0];

/** Kit families are just two interchangeable sets of figures. */
export const familyWord = (family: string | undefined): string =>
  family === "F1" ? "Kit set 1" : family === "F2" ? "Kit set 2" : (family ?? "—");

/* ----------------------------------------------------------- robot & speed */

export const paceWord = (pace: string | undefined): string =>
  pace === "slow" ? "Slow" : pace === "normal" ? "Normal" : (pace ?? "—");

export const backendWord = (backend: string | undefined): string =>
  backend === "sim"
    ? "Simulated robot"
    : backend === "ursim"
      ? "URSim rehearsal"
      : backend
        ? "UR5 arm"
        : "—";

/** Short phrase for the safety pill in the top bar. */
export function robotStatusWord(robot: {
  connected: boolean;
  busy: boolean;
  safety: string;
  latched: string | null;
} | null): { text: string; tone: Tone } {
  if (!robot) return { text: "No robot", tone: "muted" };
  if (!robot.connected) return { text: "Disconnected", tone: "err" };
  if (robot.latched) return { text: latchTitle(robot.latched), tone: "err" };
  if (robot.safety && robot.safety !== "normal") {
    return { text: safetyWord(robot.safety), tone: "warn" };
  }
  return robot.busy ? { text: "Moving", tone: "accent" } : { text: "Idle", tone: "ok" };
}

export const safetyWord = (safety: string | undefined): string =>
  ({
    normal: "Normal",
    protective_stop: "Protective stop",
    emergency_stop: "Emergency stop",
    fault: "Fault",
    violation: "Safety violation",
  })[safety ?? ""] ?? (safety ? safety.replace(/_/g, " ") : "—");

/* ---------------------------------------------------- stops & interruptions */

/** Headline for a latched stop — what happened, in three words. */
export function latchTitle(reason: string): string {
  return (
    {
      estop: "Stopped by you",
      protective_stop: "Protective stop",
      emergency_stop: "Emergency stop",
      robot_fault: "Robot fault",
    }[reason] ?? "Robot stopped"
  );
}

/**
 * Full recovery sentence for each latch reason. Every path ends at Home (which clears the
 * robot's own `latched` state and lets delivery resume with the same piece) — what differs
 * is what has to happen on the hardware first.
 */
export function latchMessage(reason: string): string | null {
  if (reason === "estop") return "Stopped by you — press Home to continue";
  if (reason === "protective_stop") return "Robot protective stop — reset in PolyScope, then Home";
  if (reason === "emergency_stop") {
    return "Emergency stop pressed — release it, re-power in PolyScope, then Home";
  }
  if (reason === "robot_fault") {
    return "Robot fault — check connection and Remote Control mode, then Home";
  }
  return null;
}

/** Just the "what to do now" half — for places where the headline already said what happened. */
export function latchAction(reason: string): string {
  return (
    {
      estop: "Press Home to continue.",
      protective_stop: "Reset the robot in PolyScope, then press Home.",
      emergency_stop: "Release the emergency stop, re-power in PolyScope, then press Home.",
      robot_fault: "Check the connection and Remote Control mode, then press Home.",
    }[reason] ?? "Press Home to continue."
  );
}

/** Why the robot is not delivering, and what the experimenter should do about it. */
export function blockedMessage(reason: string, needed: string | null, neededName?: string): string {
  const latch = latchMessage(reason);
  if (latch) return latch;
  if (reason === "mat_full") return "Mat is full — clear a spot";
  if (reason === "part_failed") {
    return "Piece could not be picked twice — press Ask for next piece to retry";
  }
  const what = neededName ?? needed;
  return `Delivery paused${what ? ` — waiting for the ${what}` : ""}`;
}

/* ------------------------------------------------------------------ figures */

/** The `kind` of a figure, as a hint the experimenter can act on. */
export const figureKindWord = (kind: string | null | undefined): string | null =>
  ({
    easy: "No time limit",
    rush: "Timed",
    rush_prime: "Timed",
    perturbed: "Timed · plan changes midway",
  })[kind ?? ""] ?? null;

/**
 * How many figures the block holds. `queue` only carries the figures still to come, so the
 * total is "the ones already done, this one, and the rest".
 */
export const figureCount = (task: KitTaskState | null): number =>
  task ? Math.max(0, task.order_index) + 1 + (task.queue?.length ?? 0) : 0;

/** Session headline used by the top bar pill. */
export function sessionHeadline(task: KitTaskState | null): { text: string; tone: Tone } {
  if (!task || task.phase === "idle") return { text: "Not started", tone: "muted" };
  if (task.phase === "between_orders") return { text: "Between figures", tone: "warn" };
  if (task.phase === "done") return { text: "Finished", tone: "ok" };
  const total = figureCount(task);
  const figure = total ? `Figure ${task.order_index + 1} of ${total}` : "Figure";
  const name = task.order_name ?? task.order_id ?? "";
  const piece = task.n_parts ? ` · piece ${task.step_index + 1}/${task.n_parts}` : "";
  return { text: `${figure}${name ? ` · ${name}` : ""}${piece}`, tone: "accent" };
}

/** mm:ss for the countdown of a timed figure. */
export function clock(seconds: number | null | undefined): string | null {
  if (seconds === null || seconds === undefined) return null;
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
