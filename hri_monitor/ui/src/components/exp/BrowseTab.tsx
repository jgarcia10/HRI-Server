import { ChevronDown, ChevronRight, Trash2 } from "lucide-react";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  api, type Experiment, type Recording, type Session, type Participant, type SignalSummary,
} from "../../lib/experiments";

// crash-proof number formatter (handles undefined/NaN from an unexpected payload)
const fmt = (n: unknown) =>
  typeof n === "number" && Number.isFinite(n) ? (Math.abs(n) >= 100 ? n.toFixed(0) : n.toFixed(2)) : "—";

function durSecs(r: Recording) {
  if (!r.stopped_at) return "—";
  return `${Math.round(r.stopped_at - r.started_at)}s`;
}

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
            <td className="tnum text-right" style={{ color: "var(--text)" }}>{fmt(st?.mean)}</td>
            <td className="tnum text-right">{fmt(st?.min)}</td>
            <td className="tnum text-right">{fmt(st?.max)}</td>
            <td className="tnum text-right">{fmt(st?.std)}</td>
            <td className="tnum text-right" style={{ color: "var(--text-muted)" }}>{st?.count ?? 0}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

type Entry = { rec: Recording; sessionId: number };

export function BrowseTab({ exp, participants }: { exp: Experiment | null; participants: Participant[] }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [open, setOpen] = useState<Record<number, SignalSummary | "loading">>({});
  const refresh = useCallback(() => {
    if (exp) api.listSessions(exp.id).then(setSessions);
    else setSessions([]);
  }, [exp]);
  useEffect(() => { refresh(); setOpen({}); }, [refresh]);

  const condName = (cid: number) => exp?.conditions.find((c) => c.id === cid)?.name ?? `condition ${cid}`;

  // Participant -> Condition -> [recordings (with their session id)], ordered by the
  // experiment's condition order, then participant roster order.
  const tree = useMemo(() => {
    const byParticipant = new Map<number, Map<number, Entry[]>>();
    for (const s of sessions) {
      let conds = byParticipant.get(s.participant_id);
      if (!conds) byParticipant.set(s.participant_id, (conds = new Map()));
      for (const rec of s.recordings) {
        if (!conds.has(rec.condition_id)) conds.set(rec.condition_id, []);
        conds.get(rec.condition_id)!.push({ rec, sessionId: s.id });
      }
    }
    return byParticipant;
  }, [sessions]);

  const orderedConditionIds = (conds: Map<number, Entry[]>) => {
    const order = exp?.conditions.map((c) => c.id) ?? [];
    const ids = [...conds.keys()];
    return ids.sort((a, b) => order.indexOf(a) - order.indexOf(b));
  };

  const toggle = async (rid: number) => {
    if (open[rid]) { setOpen((o) => { const n = { ...o }; delete n[rid]; return n; }); return; }
    setOpen((o) => ({ ...o, [rid]: "loading" }));
    const summary = await api.recordingSummary(rid);
    setOpen((o) => ({ ...o, [rid]: summary }));
  };

  const delRecording = async (e: Entry, cond: string) => {
    if (confirm(`Delete the "${cond}" recording (session #${e.sessionId}) and its data? This cannot be undone.`)) {
      await api.deleteRecording(e.rec.id);
      refresh();
    }
  };

  if (!exp) return <p className="text-sm" style={{ color: "var(--text-muted)" }}>Select an experiment.</p>;
  // participants with at least one recording, in roster order
  const pids = participants.map((p) => p.id).filter((id) => tree.has(id));
  return (
    <div className="space-y-6">
      <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>{exp.name}</h2>
      {pids.length === 0 && <p className="text-sm" style={{ color: "var(--text-muted)" }}>No sessions recorded yet.</p>}
      {pids.map((pid) => {
        const conds = tree.get(pid)!;
        const code = participants.find((p) => p.id === pid)?.code ?? `#${pid}`;
        return (
          <div key={pid} className="glass p-4">
            <h3 className="mb-3 text-sm font-semibold" style={{ color: "var(--accent)" }}>Participant {code}</h3>
            <div className="space-y-3">
              {orderedConditionIds(conds).map((cid) => {
                const entries = conds.get(cid)!;
                return (
                  <div key={cid}>
                    <div className="mb-1 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                      {condName(cid)} <span style={{ opacity: 0.7 }}>· {entries.length} session{entries.length === 1 ? "" : "s"}</span>
                    </div>
                    <table className="w-full text-xs">
                      <thead><tr style={{ color: "var(--text-muted)" }}>
                        <th className="text-left"></th><th className="py-1 text-left">Session</th>
                        <th className="text-left">Duration</th><th className="text-left">Samples</th>
                        <th className="text-left">Markers</th><th></th><th></th></tr></thead>
                      <tbody>
                        {entries.map((e) => (
                          <Fragment key={e.rec.id}>
                            <tr style={{ borderTop: "1px solid var(--glass-border)" }}>
                              <td><button onClick={() => toggle(e.rec.id)} title="Show statistics" style={{ color: "var(--text-muted)" }}>
                                {open[e.rec.id] ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</button></td>
                              <td className="py-1.5" style={{ color: "var(--text)" }}>#{e.sessionId}</td>
                              <td className="tnum">{durSecs(e.rec)}</td>
                              <td className="tnum">{e.rec.sample_count}</td>
                              <td className="tnum">{e.rec.marker_count ?? 0}</td>
                              <td><a href={`/api/recordings/${e.rec.id}/export.csv`}
                                className="rounded-md px-2 py-0.5 text-[11px] font-semibold"
                                style={{ color: "var(--accent)" }}>⬇ CSV</a></td>
                              <td><button title="Delete this recording"
                                onClick={() => delRecording(e, condName(cid))}
                                style={{ color: "var(--err)", lineHeight: 0 }}><Trash2 size={12} /></button></td>
                            </tr>
                            {open[e.rec.id] && (
                              <tr>
                                <td colSpan={7} className="px-2 pb-2">
                                  <div className="rounded-lg p-2" style={{ background: "color-mix(in srgb, var(--text-muted) 8%, transparent)" }}>
                                    {open[e.rec.id] === "loading"
                                      ? <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>computing…</span>
                                      : <StatsTable summary={open[e.rec.id] as SignalSummary} />}
                                  </div>
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
