import { ChevronDown, ChevronRight, Download, Trash2 } from "lucide-react";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  api, type Experiment, type Session, type Participant, type SignalSummary,
} from "../../lib/experiments";

function dur(s: Session["recordings"][number]) {
  if (!s.stopped_at) return "—";
  return `${Math.round(s.stopped_at - s.started_at)}s`;
}
const fmt = (n: number) => (Math.abs(n) >= 100 ? n.toFixed(0) : n.toFixed(2));
const SIGNAL_LABELS: Record<string, string> = {
  "shimmer.gsr": "GSR (µS)", "shimmer.ppg": "PPG (mV)", "ppg.hr": "HR (bpm)",
  "ppg.hrv": "HRV (ms)", "rgb.blink": "Blink (/min)",
  "thermal.forehead": "Forehead (°C)", "thermal.left_cheek": "L cheek (°C)",
  "thermal.right_cheek": "R cheek (°C)", "thermal.nose": "Nose (°C)",
};

function StatsTable({ summary }: { summary: SignalSummary }) {
  const rows = Object.entries(summary);
  if (rows.length === 0)
    return <div className="px-2 py-2 text-[11px]" style={{ color: "var(--text-muted)" }}>No samples recorded.</div>;
  return (
    <table className="w-full text-[11px]">
      <thead><tr style={{ color: "var(--text-muted)" }}>
        <th className="py-1 text-left">Signal</th><th className="text-right">Mean</th>
        <th className="text-right">Min</th><th className="text-right">Max</th>
        <th className="text-right">SD</th><th className="text-right">n</th></tr></thead>
      <tbody>
        {rows.map(([sig, st]) => (
          <tr key={sig}>
            <td className="py-0.5" style={{ color: "var(--text-muted)" }}>{SIGNAL_LABELS[sig] ?? sig}</td>
            <td className="tnum text-right" style={{ color: "var(--text)" }}>{fmt(st.mean)}</td>
            <td className="tnum text-right">{fmt(st.min)}</td>
            <td className="tnum text-right">{fmt(st.max)}</td>
            <td className="tnum text-right">{fmt(st.std)}</td>
            <td className="tnum text-right" style={{ color: "var(--text-muted)" }}>{st.count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function BrowseTab({ exp, participants }: { exp: Experiment | null; participants: Participant[] }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [open, setOpen] = useState<Record<number, SignalSummary | "loading">>({});
  const refresh = useCallback(() => {
    if (exp) api.listSessions(exp.id).then(setSessions);
    else setSessions([]);
  }, [exp]);
  useEffect(() => { refresh(); setOpen({}); }, [refresh]);

  const code = (pid: number) => participants.find((p) => p.id === pid)?.code ?? `#${pid}`;
  const condName = (cid: number) => exp?.conditions.find((c) => c.id === cid)?.name ?? "";

  // group sessions by participant, preserving participant roster order
  const grouped = useMemo(() => {
    const m = new Map<number, Session[]>();
    for (const s of sessions) {
      if (!m.has(s.participant_id)) m.set(s.participant_id, []);
      m.get(s.participant_id)!.push(s);
    }
    return m;
  }, [sessions]);

  const toggle = async (rid: number) => {
    if (open[rid]) { setOpen((o) => { const n = { ...o }; delete n[rid]; return n; }); return; }
    setOpen((o) => ({ ...o, [rid]: "loading" }));
    const summary = await api.recordingSummary(rid);
    setOpen((o) => ({ ...o, [rid]: summary }));
  };

  const delSession = async (s: Session) => {
    if (confirm(`Delete the whole session for ${code(s.participant_id)} (all ${s.recordings.length} recording(s))? This cannot be undone.`)) {
      await api.deleteSession(s.id); refresh();
    }
  };
  const delRecording = async (rid: number, cond: string) => {
    if (confirm(`Delete the "${cond}" recording and its data? This cannot be undone.`)) {
      await api.deleteRecording(rid); refresh();
    }
  };

  if (!exp) return <p className="text-sm" style={{ color: "var(--text-muted)" }}>Select an experiment.</p>;
  return (
    <div className="space-y-6">
      <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>{exp.name}</h2>
      {sessions.length === 0 && <p className="text-sm" style={{ color: "var(--text-muted)" }}>No sessions recorded yet.</p>}
      {[...grouped.entries()].map(([pid, sess]) => (
        <div key={pid} className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="rounded-full px-2.5 py-1 text-xs font-semibold"
              style={{ background: "color-mix(in srgb, var(--accent) 14%, transparent)", color: "var(--accent)" }}>
              {code(pid)}
            </span>
            <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
              {sess.length} session{sess.length === 1 ? "" : "s"}
            </span>
          </div>
          {sess.map((s) => (
            <div key={s.id} className="glass p-4">
              <div className="mb-2 flex items-center justify-between">
                <b className="text-xs" style={{ color: "var(--text-muted)" }}>session #{s.id}</b>
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
                  <th className="text-left"></th><th className="py-1 text-left">Condition</th>
                  <th className="text-left">Duration</th><th className="text-left">Samples</th>
                  <th className="text-left">Markers</th><th></th><th></th></tr></thead>
                <tbody>
                  {s.recordings.map((r) => (
                    <Fragment key={r.id}>
                      <tr style={{ borderTop: "1px solid var(--glass-border)" }}>
                        <td><button onClick={() => toggle(r.id)} title="Show statistics" style={{ color: "var(--text-muted)" }}>
                          {open[r.id] ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</button></td>
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
                      {open[r.id] && (
                        <tr>
                          <td colSpan={7} className="px-2 pb-2">
                            <div className="rounded-lg p-2" style={{ background: "color-mix(in srgb, var(--text-muted) 8%, transparent)" }}>
                              {open[r.id] === "loading"
                                ? <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>computing…</span>
                                : <StatsTable summary={open[r.id] as SignalSummary} />}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
