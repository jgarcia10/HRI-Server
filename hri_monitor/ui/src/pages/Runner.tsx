import { useState } from "react";
import {
  matCleared,
  postEvent,
  robotConnect,
  robotHome,
  robotOpenGripper,
  robotStop,
  setSupplyProfile,
  startSession,
  stopSession,
  useKitWs,
} from "../lib/kit";

const SPEECH = ["wait", "faster", "slower", "give me the red one", "put it on the left"];

// Blocked-reason copy shown to the wizard. estop/protective_stop/emergency_stop share the
// same recovery path: reset the controller if needed, then Home (which also clears the
// robot's own `latched` state and lets supply resume with the same part).
function blockedMessage(reason: string, needed: string | null): string {
  if (reason === "estop" || reason === "protective_stop" || reason === "emergency_stop") {
    return "Robot stopped — reset in PolyScope if needed, then Home";
  }
  if (reason === "mat_full") {
    return "Mat full — clear a slot (or press Mat cleared) to continue";
  }
  return `${reason}${needed ? ` — needed part ${needed}` : ""}`;
}

export function Runner() {
  const { task, robot, supply, connected } = useKitWs();
  const [participant, setParticipant] = useState("P00");
  const [condition, setCondition] = useState<"C0" | "C1">("C0");
  const [freeText, setFreeText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const call = (fn: () => Promise<unknown>) => () =>
    fn().then(() => setError(null)).catch((e) => setError(String(e.message ?? e)));

  // "active" tracks whether a session/recording exists (any phase but idle) — this is
  // what gates Start/Stop and the wizard controls. "done" still has an active session
  // (Stop must remain enabled) until session.stop() tears it down and the engine
  // publishes a fresh idle task.state.
  const active = task !== null && task.phase !== "idle";

  return (
    <div className="space-y-4 p-2">
      <h2 className="text-xl font-semibold">Kit Study — wizard</h2>
      {!connected && <p className="text-amber-500">WS disconnected…</p>}
      {error && <p className="text-red-500">{error}</p>}

      <section className="glass flex items-end gap-3 p-4">
        <label className="flex flex-col text-sm">
          Participant
          <input className="rounded border bg-transparent p-1" value={participant}
                 onChange={(e) => setParticipant(e.target.value)} />
        </label>
        <label className="flex flex-col text-sm">
          Condition
          <select className="rounded border bg-transparent p-1" value={condition}
                  onChange={(e) => setCondition(e.target.value as "C0" | "C1")}>
            <option>C0</option>
            <option>C1</option>
          </select>
        </label>
        <button className="rounded bg-emerald-600 px-4 py-2 text-white disabled:opacity-40"
                disabled={active}
                onClick={call(() => startSession({ participant_code: participant, condition }))}>
          Start block
        </button>
        <button className="rounded bg-red-600 px-4 py-2 text-white disabled:opacity-40"
                disabled={!active} onClick={call(stopSession)}>
          Stop
        </button>
      </section>

      <section className="glass p-4">
        <p className="text-sm text-slate-400">
          {task
            ? `phase=${task.phase} · order=${task.order_id ?? "—"} (${task.kind ?? "—"}) · ` +
              `step ${task.step_index + 1}/${task.n_parts} · ` +
              `remaining ${task.remaining_s ?? "—"}s` +
              (supply?.failed && supply.failed.length > 0 ? ` · failed: ${supply.failed.join(", ")}` : "")
            : "no task state yet"}
        </p>
        {task?.current_part && (
          <p className="text-lg">
            Current part: <b>{task.current_part.type} {task.current_part.color}</b>{" "}
            (slot {task.current_part.depot_slot})
          </p>
        )}
      </section>

      <section className="glass p-4">
        <div className="flex items-center gap-3">
          <span className={`inline-block h-3 w-3 rounded-full ${robot?.safety === "normal" ? "bg-emerald-500" : "bg-red-500"}`} />
          <p className="text-sm">
            Robot: <b>{robot?.backend ?? "—"}</b> · {robot?.connected ? "connected" : "disconnected"} ·
            safety {robot?.safety ?? "—"} · {robot?.busy ? "busy" : "idle"} · queue {robot?.queue ?? 0} ·
            gripper {robot?.gripper_closed ? "closed" : "open"} · pace {robot?.pace ?? "—"}
          </p>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button className="rounded bg-slate-600 px-3 py-2 text-white" onClick={call(robotHome)}>Home</button>
          <button className="rounded bg-slate-600 px-3 py-2 text-white" onClick={call(robotOpenGripper)}>Open gripper</button>
          <button className="rounded bg-red-700 px-5 py-2 text-lg font-bold text-white" onClick={call(robotStop)}>■ STOP robot</button>
          {robot && !robot.connected && (
            <button className="rounded bg-amber-600 px-3 py-2 text-white" onClick={call(robotConnect)}>
              Reconnect
            </button>
          )}
        </div>
        {robot?.latched && (
          <div className="mt-3 rounded bg-red-600/20 px-3 py-2 text-sm font-semibold text-red-600">
            ⛔ LATCHED: {robot.latched} — press Home to resume
          </div>
        )}
      </section>

      <section className="glass p-4">
        <p className="mb-2 text-sm text-slate-400">Supply profile (live) · next: {supply?.next_part_id ?? "—"}</p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-sm">Look-ahead
            <select className="rounded border bg-transparent p-1" value={supply?.profile.lookahead ?? 1}
                    disabled={!active} onChange={(e) => call(() => setSupplyProfile({ lookahead: Number(e.target.value) }))()}>
              {[0, 1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <label className="flex flex-col text-sm">Side
            <select className="rounded border bg-transparent p-1" value={supply?.profile.side ?? "C"}
                    disabled={!active} onChange={(e) => call(() => setSupplyProfile({ side: e.target.value }))()}>
              {["L", "C", "R"].map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
          <label className="flex flex-col text-sm">Pace
            <select className="rounded border bg-transparent p-1" value={supply?.profile.pace ?? "normal"}
                    disabled={!active} onChange={(e) => call(() => setSupplyProfile({ pace: e.target.value }))()}>
              {["slow", "normal"].map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
          <button className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-40"
                  disabled={!active || ((supply?.profile.lookahead ?? 1) !== 0 && supply?.blocked?.reason !== "part_failed")}
                  onClick={call(() => postEvent("request_part"))}>
            Request next part
          </button>
        </div>
        {supply?.blocked && (
          <div className="mt-3 rounded bg-amber-500/20 px-3 py-2 text-sm text-amber-600">
            ⚠ Supply blocked: {blockedMessage(supply.blocked.reason, supply.blocked.needed)}
            <div className="mt-2 flex flex-wrap gap-2">
              <button className="rounded bg-amber-600 px-3 py-1 text-sm text-white" disabled={!active}
                      onClick={call(() => postEvent("slot_cleared", { slot: "L" }))}>
                Slot cleared L
              </button>
              <button className="rounded bg-amber-600 px-3 py-1 text-sm text-white" disabled={!active}
                      onClick={call(() => postEvent("slot_cleared", { slot: "C" }))}>
                Slot cleared C
              </button>
              <button className="rounded bg-amber-600 px-3 py-1 text-sm text-white" disabled={!active}
                      onClick={call(() => postEvent("slot_cleared", { slot: "R" }))}>
                Slot cleared R
              </button>
              <button className="rounded bg-amber-700 px-3 py-1 text-sm text-white" disabled={!active}
                      onClick={call(matCleared)}>
                Mat cleared
              </button>
            </div>
          </div>
        )}
        <div className="mt-3 grid grid-cols-3 gap-2">
          {(["L", "C", "R"] as const).map((slot) => (
            <div key={slot} className="rounded border p-2 text-center text-sm">
              <div className="text-slate-400">{slot}</div>
              <div className="font-mono">{supply?.staged?.[slot] ?? (supply?.inflight?.length ? "…" : "—")}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="glass flex flex-wrap gap-3 p-4">
        <button className="rounded bg-blue-600 px-6 py-3 text-lg text-white disabled:opacity-40"
                disabled={!active || task?.phase !== "running"}
                onClick={call(() => postEvent("part_placed"))}>
          ✔ Part placed
        </button>
        <button className="rounded bg-slate-600 px-4 py-3 text-white disabled:opacity-40"
                disabled={task?.phase !== "between_orders"}
                onClick={call(() => postEvent("next_order"))}>
          ▶ Next order
        </button>
        <button className="rounded bg-amber-700 px-4 py-3 text-white disabled:opacity-40"
                disabled={!active}
                onClick={call(matCleared)}>
          Mat cleared
        </button>
        {(["L", "C", "R"] as const).map((slot) => (
          <button key={slot} className="rounded bg-purple-600 px-4 py-3 text-white"
                  disabled={!active}
                  onClick={call(() => postEvent("reposition", { slot }))}>
            Repositioned → {slot}
          </button>
        ))}
      </section>

      <section className="glass flex flex-wrap items-center gap-2 p-4">
        {SPEECH.map((s) => (
          <button key={s} className="rounded border px-3 py-2 text-sm" disabled={!active}
                  onClick={call(() => postEvent("speech", { text: s }))}>
            "{s}"
          </button>
        ))}
        <input className="min-w-64 flex-1 rounded border bg-transparent p-2 text-sm"
               placeholder="free-text speech…" value={freeText}
               onChange={(e) => setFreeText(e.target.value)} />
        <button className="rounded border px-3 py-2 text-sm" disabled={!active || !freeText}
                onClick={call(() => postEvent("speech", { text: freeText }).then(() => setFreeText("")))}>
          Send
        </button>
      </section>
    </div>
  );
}
