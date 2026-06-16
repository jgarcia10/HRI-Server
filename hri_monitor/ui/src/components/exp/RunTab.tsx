import { Eye, HeartPulse, Square, Thermometer, Waves } from "lucide-react";
import { useState } from "react";
import { api, type Experiment, type Participant, type ActiveStatus } from "../../lib/experiments";
import { useLiveData } from "../../lib/ws";
import { SignalChart } from "../SignalChart";
import { Field, Select } from "../DeviceCard";

function fmt(s: number) {
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export function RunTab({ exp, participants, active }: {
  exp: Experiment | null; participants: Participant[]; active: ActiveStatus;
}) {
  const { latest, series } = useLiveData();
  const [participantId, setParticipantId] = useState<number | null>(null);
  const [conditionId, setConditionId] = useState<number | null>(null);
  const [text, setText] = useState("");
  const temps = latest["thermal.temps"];
  const recId = active?.recording_id ?? null;

  const start = async () => {
    if (exp && participantId && conditionId)
      await api.start({ experiment_id: exp.id, participant_id: participantId, condition_id: conditionId });
  };

  return (
    <div className="space-y-4">
      <div className="glass p-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <Field label="Participant">
            <Select value={participantId ?? ""} onChange={(e) => setParticipantId(Number(e.target.value))}>
              <option value="">— select —</option>
              {participants.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
            </Select>
          </Field>
          <Field label="Condition">
            <div className="flex flex-wrap gap-2">
              {exp?.conditions.map((c) => (
                <button key={c.id} onClick={() => setConditionId(c.id)}
                  className="rounded-full px-3 py-1 text-xs font-semibold"
                  style={conditionId === c.id
                    ? { background: "color-mix(in srgb, var(--accent) 18%, transparent)", color: "var(--accent)", border: "1px solid var(--accent)" }
                    : { color: "var(--text-muted)", border: "1px solid var(--glass-border)" }}>{c.name}</button>
              ))}
            </div>
          </Field>
        </div>
      </div>

      {active ? (
        <div className="glass flex items-center justify-between p-4">
          <div className="flex items-center gap-3">
            <span className="h-2.5 w-2.5 rounded-full motion-safe:animate-[pulse-dot_1.4s_infinite]"
              style={{ background: "var(--err)", boxShadow: "0 0 10px var(--err)" }} />
            <div>
              <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                Recording · {active.condition}
              </div>
              <div className="tnum text-2xl font-bold">{fmt(active.elapsed)}
                <span className="ml-2 text-sm" style={{ color: "var(--text-muted)" }}>· {active.sample_count} samples</span>
              </div>
            </div>
          </div>
          <button onClick={() => recId && api.stop(recId)}
            className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-bold"
            style={{ background: "var(--err)", color: "#0b1220" }}><Square size={14} /> Stop</button>
        </div>
      ) : (
        <button onClick={start} disabled={!exp || !participantId || !conditionId}
          className="glass w-full p-3 text-sm font-bold disabled:opacity-50"
          style={{ color: "var(--ok)" }}>● Start recording</button>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SignalChart title="GSR" unit="µS" colorVar="--chart-gsr" icon={Waves}
          points={series["shimmer.gsr"] ?? []} value={latest["shimmer.gsr"]?.value} />
        <SignalChart title="HR" unit="bpm" colorVar="--chart-ppg" icon={HeartPulse} glow={false}
          points={series["ppg.hr"] ?? []} value={latest["ppg.hr"]?.value} />
        <SignalChart title="Blink" unit="/min" colorVar="--chart-blink" icon={Eye}
          points={series["rgb.blink"] ?? []} value={latest["rgb.blink"]?.rate} />
        <SignalChart title="Forehead" unit="°C" colorVar="--chart-temp" icon={Thermometer}
          points={series["thermal.temps"] ?? []} value={temps?.forehead} />
      </div>

      <div className="glass p-4">
        <div className="mb-2 text-[10px] uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Markers</div>
        <div className="mb-2 flex flex-wrap gap-2">
          {exp?.marker_labels.map((l) => (
            <button key={l.id} disabled={!recId} onClick={() => recId && api.marker(recId, l.label, "button")}
              className="rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-40"
              style={{ background: "color-mix(in srgb, var(--accent) 12%, transparent)", color: "var(--accent)" }}>{l.label}</button>
          ))}
        </div>
        <div className="flex gap-2">
          <input className="flex-1 rounded-lg border px-2 py-1 text-xs" value={text} disabled={!recId}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && recId && text.trim()) { api.marker(recId, text.trim(), "text"); setText(""); } }}
            placeholder="Custom marker + Enter"
            style={{ borderColor: "var(--glass-border)", background: "var(--glass-bg)", color: "var(--text)" }} />
        </div>
        {active && active.markers.length > 0 && (
          <table className="mt-3 w-full text-xs">
            <tbody>
              {active.markers.map((m) => (
                <tr key={m.id}>
                  <td className="tnum py-1" style={{ color: "var(--text-muted)" }}>{fmt(m.t_offset)}</td>
                  <td>{m.label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
