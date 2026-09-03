import type { ReactNode } from "react";
import { useKitWs, type KitTaskState } from "../lib/kit";

const BRICK: Record<string, string> = {
  red: "#d64541", blue: "#2e86de", green: "#27ae60", yellow: "#f1c40f",
};
const WIDTH: Record<string, number> = { "2x2": 90, "2x3": 130, "2x4": 170, L: 120 };

function Diagram({ task }: { task: KitTaskState }) {
  // Column of bricks, bottom-up = assembly sequence. Done = solid, current = pulsing
  // outline, future = dimmed. We only know types/colors of the CURRENT part from
  // task.state, so the diagram shows progress boxes + the current part in detail.
  const rows = [];
  for (let i = 0; i < task.n_parts; i++) {
    const done = i < task.step_index;
    const isCurrent = i === task.step_index && task.phase === "running";
    const part = isCurrent ? task.current_part : null;
    const w = part ? WIDTH[part.type] ?? 120 : 120;
    const fill = done ? "#5b6a79" : part ? BRICK[part.color] ?? "#888" : "transparent";
    rows.unshift(
      <div key={i} className="flex items-center justify-center" style={{ height: 56 }}>
        <div
          style={{
            width: w, height: 44, borderRadius: 8, background: fill,
            border: isCurrent ? "4px solid white" : "2px solid #5b6a79",
            opacity: done ? 0.5 : 1,
            boxShadow: isCurrent ? "0 0 24px rgba(255,255,255,.7)" : undefined,
          }}
        >
          {part && (
            <div className="flex h-full items-center justify-center text-lg font-bold text-white">
              {part.type} · {part.color}
            </div>
          )}
        </div>
      </div>,
    );
  }
  return <div className="flex flex-col-reverse">{rows.reverse()}</div>;
}

export function Screen() {
  const { task, connected } = useKitWs();
  if (!task || task.phase === "idle") {
    return (
      <Full>
        <p className="text-4xl text-slate-400">
          {connected ? "Waiting for the session to start…" : "Connecting…"}
        </p>
      </Full>
    );
  }
  if (task.phase === "done") {
    return <Full><p className="text-5xl">Block complete — thank you!</p></Full>;
  }
  if (task.phase === "between_orders") {
    return <Full><p className="text-5xl">Order complete ✓<br />Next order coming up…</p></Full>;
  }
  const low = task.remaining_s !== null && task.remaining_s <= 30;
  return (
    <Full>
      <div className="flex w-full max-w-5xl items-start justify-between gap-10 px-10">
        <div>
          <p className="mb-2 text-2xl uppercase tracking-widest text-slate-400">
            Order {task.order_index + 1}/6 · {task.kind}
          </p>
          <p className="mb-6 text-3xl">
            Step {task.step_index + 1} of {task.n_parts}
          </p>
          <Diagram task={task} />
          {task.perturbation_applied && (
            <p className="mt-6 animate-pulse text-3xl font-bold text-amber-400">
              ⚠ Order changed — check the diagram
            </p>
          )}
        </div>
        <div className="text-right">
          <p className="text-2xl uppercase tracking-widest text-slate-400">Time</p>
          <p className={`font-mono text-8xl font-bold ${low ? "animate-pulse text-red-500" : ""}`}>
            {task.remaining_s === null ? "—" : `${Math.ceil(task.remaining_s)}s`}
          </p>
          <p className="mt-8 text-xl text-slate-400">Coming up: {task.queue.join(" · ") || "—"}</p>
        </div>
      </div>
    </Full>
  );
}

function Full({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-900 text-center text-white">
      {children}
    </div>
  );
}
