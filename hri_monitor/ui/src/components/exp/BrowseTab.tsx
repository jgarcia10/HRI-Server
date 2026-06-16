import { Download, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, type Experiment, type Session, type Participant } from "../../lib/experiments";

function dur(s: Session["recordings"][number]) {
  if (!s.stopped_at) return "—";
  return `${Math.round(s.stopped_at - s.started_at)}s`;
}

export function BrowseTab({ exp, participants }: { exp: Experiment | null; participants: Participant[] }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const refresh = useCallback(() => {
    if (exp) api.listSessions(exp.id).then(setSessions);
    else setSessions([]);
  }, [exp]);
  useEffect(() => { refresh(); }, [refresh]);
  const code = (pid: number) => participants.find((p) => p.id === pid)?.code ?? `#${pid}`;
  const condName = (cid: number) => exp?.conditions.find((c) => c.id === cid)?.name ?? "";

  const delSession = async (s: Session) => {
    if (confirm(`Delete the whole session for ${code(s.participant_id)} (all ${s.recordings.length} recording(s))? This cannot be undone.`)) {
      await api.deleteSession(s.id);
      refresh();
    }
  };
  const delRecording = async (rid: number, cond: string) => {
    if (confirm(`Delete the "${cond}" recording and its data? This cannot be undone.`)) {
      await api.deleteRecording(rid);
      refresh();
    }
  };

  if (!exp) return <p className="text-sm" style={{ color: "var(--text-muted)" }}>Select an experiment.</p>;
  return (
    <div className="space-y-4">
      {sessions.length === 0 && <p className="text-sm" style={{ color: "var(--text-muted)" }}>No sessions recorded yet.</p>}
      {sessions.map((s) => (
        <div key={s.id} className="glass p-4">
          <div className="mb-2 flex items-center justify-between">
            <b className="text-sm" style={{ color: "var(--text)" }}>{code(s.participant_id)} · session #{s.id}</b>
            <div className="flex items-center gap-2">
              <a href={`/api/sessions/${s.id}/export.zip`}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold"
                style={{ background: "color-mix(in srgb, var(--accent) 12%, transparent)", color: "var(--accent)" }}>
                <Download size={13} /> Session .zip
              </a>
              <button title="Delete this whole session" onClick={() => delSession(s)}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold"
                style={{ background: "color-mix(in srgb, var(--err) 12%, transparent)", color: "var(--err)" }}>
                <Trash2 size={13} /> Delete
              </button>
            </div>
          </div>
          <table className="w-full text-xs">
            <thead><tr style={{ color: "var(--text-muted)" }}>
              <th className="py-1 text-left">Condition</th><th className="text-left">Duration</th>
              <th className="text-left">Samples</th><th className="text-left">Markers</th><th></th><th></th></tr></thead>
            <tbody>
              {s.recordings.map((r) => (
                <tr key={r.id} style={{ borderTop: "1px solid var(--glass-border)" }}>
                  <td className="py-1.5" style={{ color: "var(--accent)" }}>{condName(r.condition_id)}</td>
                  <td className="tnum">{dur(r)}</td>
                  <td className="tnum">{r.sample_count}</td>
                  <td className="tnum">{r.marker_count ?? 0}</td>
                  <td><a href={`/api/recordings/${r.id}/export.csv`}
                    className="rounded-md px-2 py-0.5 text-[11px] font-semibold"
                    style={{ color: "var(--accent)" }}>⬇ CSV</a></td>
                  <td><button title="Delete this recording"
                    onClick={() => delRecording(r.id, condName(r.condition_id))}
                    style={{ color: "var(--err)", lineHeight: 0 }}><Trash2 size={12} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
