import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Experiment, type Participant } from "../../lib/experiments";
import { Field } from "../DeviceCard";

export function ManageTab({
  experiments, selected, onSelect, exp, participants, refresh, refreshList,
}: {
  experiments: Experiment[];
  selected: number | null;
  onSelect: (id: number | null) => void;
  exp: Experiment | null;
  participants: Participant[];
  refresh: () => void;
  refreshList: () => void;
}) {
  const [newExp, setNewExp] = useState("");
  const [condText, setCondText] = useState("");
  const [labelText, setLabelText] = useState("");
  const [pcode, setPcode] = useState("");

  useEffect(() => {
    setCondText(exp ? exp.conditions.map((c) => c.name).join(", ") : "");
    setLabelText(exp ? exp.marker_labels.map((l) => l.label).join(", ") : "");
  }, [exp?.id]);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="glass p-4">
        <h3 className="mb-2 text-sm font-medium" style={{ color: "var(--text-muted)" }}>Experiments</h3>
        <div className="space-y-1">
          {experiments.map((e) => (
            <div key={e.id} className="flex items-center gap-1 rounded-lg"
              style={selected === e.id ? { background: "color-mix(in srgb, var(--accent) 12%, transparent)" } : undefined}>
              <button onClick={() => onSelect(e.id)}
                className="flex-1 px-3 py-2 text-left text-sm"
                style={{ color: selected === e.id ? "var(--accent)" : "var(--text)" }}>
                {e.name}
              </button>
              <button title="Delete experiment (all participants, sessions, recordings)"
                onClick={async () => {
                  if (confirm(`Delete experiment "${e.name}" and ALL its participants, sessions and recordings? This cannot be undone.`)) {
                    await api.deleteExperiment(e.id);
                    if (selected === e.id) onSelect(null);
                    refreshList();
                  }
                }}
                className="px-2 py-2" style={{ color: "var(--err)" }}><Trash2 size={13} /></button>
            </div>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <input className="flex-1 rounded-lg border px-2 py-1 text-xs" value={newExp}
            onChange={(e) => setNewExp(e.target.value)} placeholder="New experiment name"
            style={{ borderColor: "var(--glass-border)", background: "var(--glass-bg)", color: "var(--text)" }} />
          <button onClick={async () => { if (newExp.trim()) { const r = await api.createExperiment(newExp.trim()); setNewExp(""); refreshList(); onSelect(r.id); } }}
            className="rounded-lg px-3 text-xs font-semibold" style={{ background: "var(--accent)", color: "#fff" }}>
            <Plus size={14} />
          </button>
        </div>
      </div>

      {exp && (
        <div className="glass p-4 lg:col-span-2 space-y-3">
          <h3 className="text-sm font-medium" style={{ color: "var(--text)" }}>{exp.name}</h3>
          <Field label="Conditions">
            <div className="flex gap-2">
              <input className="flex-1 rounded-lg border px-2 py-1 text-xs"
                value={condText}
                onChange={(e) => setCondText(e.target.value)}
                placeholder="Comma-separated, in order"
                style={{ borderColor: "var(--glass-border)", background: "var(--glass-bg)", color: "var(--text)" }} />
              <button onClick={async () => { await api.setConditions(exp.id, condText.split(",").map(s => s.trim()).filter(Boolean)); refresh(); }}
                className="rounded-lg px-3 text-xs font-semibold" style={{ color: "var(--accent)", background: "color-mix(in srgb, var(--accent) 12%, transparent)" }}>Save</button>
            </div>
          </Field>
          <Field label="Marker labels">
            <div className="flex gap-2">
              <input className="flex-1 rounded-lg border px-2 py-1 text-xs"
                value={labelText}
                onChange={(e) => setLabelText(e.target.value)}
                placeholder="Comma-separated quick-buttons"
                style={{ borderColor: "var(--glass-border)", background: "var(--glass-bg)", color: "var(--text)" }} />
              <button onClick={async () => { await api.setMarkerLabels(exp.id, labelText.split(",").map(s => s.trim()).filter(Boolean)); refresh(); }}
                className="rounded-lg px-3 text-xs font-semibold" style={{ color: "var(--accent)", background: "color-mix(in srgb, var(--accent) 12%, transparent)" }}>Save</button>
            </div>
          </Field>
          <div>
            <h4 className="mb-1 text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Participants</h4>
            <div className="flex flex-wrap gap-2">
              {participants.map((p) => (
                <span key={p.id} className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs"
                  style={{ background: "color-mix(in srgb, var(--accent) 10%, transparent)", color: "var(--accent)" }}>
                  {p.code}
                  <button title={`Delete ${p.code} and all their sessions/recordings`}
                    onClick={async () => {
                      if (confirm(`Delete participant "${p.code}" and ALL their sessions and recordings? This cannot be undone.`)) {
                        await api.deleteParticipant(p.id);
                        refresh();
                      }
                    }}
                    style={{ color: "var(--err)", lineHeight: 0 }}><Trash2 size={11} /></button>
                </span>
              ))}
            </div>
            <div className="mt-2 flex gap-2">
              <input className="flex-1 rounded-lg border px-2 py-1 text-xs" value={pcode}
                onChange={(e) => setPcode(e.target.value)} placeholder="New participant code (e.g. P04)"
                style={{ borderColor: "var(--glass-border)", background: "var(--glass-bg)", color: "var(--text)" }} />
              <button onClick={async () => { if (pcode.trim()) { await api.createParticipant(exp.id, pcode.trim()); setPcode(""); refresh(); } }}
                className="rounded-lg px-3 text-xs font-semibold" style={{ background: "var(--accent)", color: "#fff" }}>Add</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
