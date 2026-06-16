import { useState } from "react";
import { ResultBlock } from "../components/analysis/ResultBlock";
import {
  type AnalysisResult, type CompareReq, analysisApi, useAnalysisOptions,
  FEATURE_LABELS, SIGNAL_LABELS,
} from "../lib/analysis";
import { useExperiments } from "../lib/experiments";

export function Analysis() {
  const { experiments } = useExperiments();
  const [expId, setExpId] = useState<number | null>(null);
  const options = useAnalysisOptions(expId);

  const [signal, setSignal] = useState<string>("");
  const [features, setFeatures] = useState<string[]>(["mean"]);
  const [condIds, setCondIds] = useState<number[]>([]);
  const [unit, setUnit] = useState<"participant" | "recording">("participant");
  const [results, setResults] = useState<AnalysisResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastReq, setLastReq] = useState<CompareReq | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toggle = <T,>(arr: T[], v: T) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  const onPickExp = (id: number) => {
    setExpId(id); setSignal(""); setCondIds([]); setResults(null);
  };

  const canRun = expId != null && signal && features.length > 0 && condIds.length >= 2 && !busy;

  const run = async () => {
    if (expId == null) return;
    const req: CompareReq = { experiment_id: expId, condition_ids: condIds, signal, features, unit };
    setBusy(true); setLastReq(req); setError(null);
    try {
      const r = await analysisApi.compare(req);
      setResults(r.results);
    } catch {
      setResults(null);
      setError("Analysis request failed. Check that the server is running and try again.");
    } finally { setBusy(false); }
  };

  const lbl = { fontSize: 10, textTransform: "uppercase" as const, letterSpacing: "0.05em", color: "var(--text-muted)" };

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>Analysis</h2>

      {/* control bar */}
      <div className="glass space-y-3 p-4">
        <div className="grid gap-3 md:grid-cols-3">
          <div>
            <div style={lbl} className="mb-1">Experiment</div>
            <select className="an-sel" value={expId ?? ""}
              onChange={(e) => onPickExp(Number(e.target.value))}>
              <option value="" disabled>Select…</option>
              {experiments.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
          </div>
          <div>
            <div style={lbl} className="mb-1">Signal</div>
            <select className="an-sel" value={signal} onChange={(e) => setSignal(e.target.value)}
              disabled={!options}>
              <option value="" disabled>Select…</option>
              {options?.signals.map((s) => <option key={s} value={s}>{SIGNAL_LABELS[s] ?? s}</option>)}
            </select>
          </div>
          <div>
            <div style={lbl} className="mb-1">Unit of analysis</div>
            <div className="flex gap-2">
              {(["participant", "recording"] as const).map((u) => (
                <button key={u} onClick={() => setUnit(u)}
                  className="rounded-full px-3 py-1 text-[11px] font-semibold"
                  style={unit === u
                    ? { background: "color-mix(in srgb, var(--accent) 18%, transparent)", color: "var(--accent)", border: "1px solid var(--accent)" }
                    : { color: "var(--text-muted)", border: "1px solid color-mix(in srgb, var(--text-muted) 30%, transparent)" }}>
                  {u === "participant" ? "Per participant" : "Per recording"}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div>
          <div style={lbl} className="mb-1">Features</div>
          <div className="flex flex-wrap gap-2">
            {options?.features.map((f) => (
              <button key={f} onClick={() => setFeatures((a) => toggle(a, f))}
                className="rounded-full px-3 py-1 text-[11px] font-semibold"
                style={features.includes(f)
                  ? { background: "color-mix(in srgb, var(--accent) 18%, transparent)", color: "var(--accent)", border: "1px solid var(--accent)" }
                  : { color: "var(--text-muted)", border: "1px solid color-mix(in srgb, var(--text-muted) 30%, transparent)" }}>
                {FEATURE_LABELS[f] ?? f}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div style={lbl} className="mb-1">Conditions to compare (pick ≥ 2)</div>
          <div className="flex flex-wrap gap-2">
            {options?.conditions.map((c) => (
              <button key={c.id} onClick={() => setCondIds((a) => toggle(a, c.id))}
                className="rounded-full px-3 py-1 text-[11px] font-semibold"
                style={condIds.includes(c.id)
                  ? { background: "color-mix(in srgb, var(--accent) 18%, transparent)", color: "var(--accent)", border: "1px solid var(--accent)" }
                  : { color: "var(--text-muted)", border: "1px solid color-mix(in srgb, var(--text-muted) 30%, transparent)" }}>
                {c.name}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center">
          <button onClick={run} disabled={!canRun}
            className="ml-auto rounded-lg px-5 py-2 text-sm font-bold"
            style={{ background: canRun ? "var(--accent)" : "color-mix(in srgb, var(--accent) 40%, transparent)",
                     color: "var(--base)", cursor: canRun ? "pointer" : "not-allowed" }}>
            {busy ? "Running…" : "▸ Run analysis"}
          </button>
        </div>
      </div>

      {error && (
        <div className="glass p-4 text-sm" style={{ color: "var(--err)" }}>{error}</div>
      )}

      {/* results: one block per feature */}
      {results && lastReq && results.length === 0 && (
        <div className="glass p-4 text-sm" style={{ color: "var(--text-muted)" }}>No results.</div>
      )}
      {results && lastReq && results.map((res, i) => (
        <ResultBlock key={`${res.feature}-${i}`} res={res} req={lastReq} />
      ))}
    </div>
  );
}
