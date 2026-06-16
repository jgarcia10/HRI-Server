import { Download } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Experiment, type Session, type Participant } from "../../lib/experiments";

function dur(s: Session["recordings"][number]) {
  if (!s.stopped_at) return "—";
  return `${Math.round(s.stopped_at - s.started_at)}s`;
}

export function BrowseTab({ exp, participants }: { exp: Experiment | null; participants: Participant[] }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  useEffect(() => { if (exp) api.listSessions(exp.id).then(setSessions); else setSessions([]); }, [exp]);
  const code = (pid: number) => participants.find((p) => p.id === pid)?.code ?? `#${pid}`;
  const condName = (cid: number) => exp?.conditions.find((c) => c.id === cid)?.name ?? "";

  if (!exp) return <p className="text-sm" style={{ color: "var(--text-muted)" }}>Select an experiment.</p>;
  return (
    <div className="space-y-4">
      {sessions.length === 0 && <p className="text-sm" style={{ color: "var(--text-muted)" }}>No sessions recorded yet.</p>}
      {sessions.map((s) => (
        <div key={s.id} className="glass p-4">
          <div className="mb-2 flex items-center justify-between">
            <b className="text-sm" style={{ color: "var(--text)" }}>{code(s.participant_id)} · session #{s.id}</b>
            <a href={`/api/sessions/${s.id}/export.zip`}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold"
              style={{ background: "color-mix(in srgb, var(--accent) 12%, transparent)", color: "var(--accent)" }}>
              <Download size={13} /> Session .zip
            </a>
          </div>
          <table className="w-full text-xs">
            <thead><tr style={{ color: "var(--text-muted)" }}>
              <th className="py-1 text-left">Condition</th><th className="text-left">Duration</th>
              <th className="text-left">Samples</th><th className="text-left">Markers</th><th></th></tr></thead>
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
