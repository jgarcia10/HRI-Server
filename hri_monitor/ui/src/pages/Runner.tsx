import { useState } from "react";
import { postEvent, startSession, stopSession, useKitWs } from "../lib/kit";

const SPEECH = ["wait", "faster", "slower", "give me the red one", "put it on the left"];

export function Runner() {
  const { task, connected } = useKitWs();
  const [participant, setParticipant] = useState("P00");
  const [condition, setCondition] = useState<"C0" | "C1">("C0");
  const [freeText, setFreeText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const call = (fn: () => Promise<unknown>) => () =>
    fn().then(() => setError(null)).catch((e) => setError(String(e.message ?? e)));

  const running = task !== null && task.phase !== "idle" && task.phase !== "done";

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
                disabled={running}
                onClick={call(() => startSession({ participant_code: participant, condition }))}>
          Start block
        </button>
        <button className="rounded bg-red-600 px-4 py-2 text-white disabled:opacity-40"
                disabled={!running} onClick={call(stopSession)}>
          Stop
        </button>
      </section>

      <section className="glass p-4">
        <p className="text-sm text-slate-400">
          {task
            ? `phase=${task.phase} · order=${task.order_id ?? "—"} (${task.kind ?? "—"}) · ` +
              `step ${task.step_index + 1}/${task.n_parts} · ` +
              `remaining ${task.remaining_s ?? "—"}s`
            : "no task state yet"}
        </p>
        {task?.current_part && (
          <p className="text-lg">
            Current part: <b>{task.current_part.type} {task.current_part.color}</b>{" "}
            (slot {task.current_part.depot_slot})
          </p>
        )}
      </section>

      <section className="glass flex flex-wrap gap-3 p-4">
        <button className="rounded bg-blue-600 px-6 py-3 text-lg text-white disabled:opacity-40"
                disabled={!running || task?.phase !== "running"}
                onClick={call(() => postEvent("part_placed"))}>
          ✔ Part placed
        </button>
        <button className="rounded bg-slate-600 px-4 py-3 text-white disabled:opacity-40"
                disabled={task?.phase !== "between_orders"}
                onClick={call(() => postEvent("next_order"))}>
          ▶ Next order
        </button>
        {(["L", "C", "R"] as const).map((slot) => (
          <button key={slot} className="rounded bg-purple-600 px-4 py-3 text-white"
                  disabled={!running}
                  onClick={call(() => postEvent("reposition", { slot }))}>
            Repositioned → {slot}
          </button>
        ))}
      </section>

      <section className="glass flex flex-wrap items-center gap-2 p-4">
        {SPEECH.map((s) => (
          <button key={s} className="rounded border px-3 py-2 text-sm" disabled={!running}
                  onClick={call(() => postEvent("speech", { text: s }))}>
            "{s}"
          </button>
        ))}
        <input className="min-w-64 flex-1 rounded border bg-transparent p-2 text-sm"
               placeholder="free-text speech…" value={freeText}
               onChange={(e) => setFreeText(e.target.value)} />
        <button className="rounded border px-3 py-2 text-sm" disabled={!running || !freeText}
                onClick={call(() => postEvent("speech", { text: freeText }).then(() => setFreeText("")))}>
          Send
        </button>
      </section>
    </div>
  );
}
