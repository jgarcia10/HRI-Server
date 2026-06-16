import { type AnalysisResult, type CompareReq, analysisApi, FEATURE_LABELS, SIGNAL_LABELS } from "../../lib/analysis";

const fmt = (n: unknown, d = 2) =>
  typeof n === "number" && Number.isFinite(n) ? n.toFixed(d) : "—";

function downloadBlob(data: string, type: string, filename: string) {
  const blob = new Blob([data], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  a.click(); URL.revokeObjectURL(url);
}

function downloadJson(res: AnalysisResult) {
  downloadBlob(JSON.stringify(res, null, 2), "application/json",
    `analysis_${res.signal ?? "signal"}_${res.feature}.json`);
}

// RFC4180-style CSV field escaping: quote if the field contains comma/quote/newline
function csvField(v: unknown): string {
  const s = String(v);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function downloadCsv(res: AnalysisResult) {
  const rows = ["condition,subject,signal,feature,value"];
  for (const v of res.values ?? [])
    rows.push([v.condition, v.subject, res.signal ?? "", res.feature, v.value].map(csvField).join(","));
  downloadBlob(rows.join("\n"), "text/csv", `analysis_${res.signal ?? "signal"}_${res.feature}_values.csv`);
}

export function ResultBlock({ res, req }: { res: AnalysisResult; req: CompareReq }) {
  const featLabel = FEATURE_LABELS[res.feature] ?? res.feature;
  const sigLabel = SIGNAL_LABELS[res.signal ?? ""] ?? res.signal ?? "";

  if (!res.ok) {
    return (
      <div className="glass p-4">
        <div className="mb-1 text-sm font-semibold" style={{ color: "var(--text)" }}>{featLabel} · {sigLabel}</div>
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>{res.reason ?? "could not compute"}</div>
        {res.descriptives && (
          <div className="mt-2 text-[11px]" style={{ color: "var(--text-muted)" }}>
            {res.descriptives.map((d) => `${d.condition}: n=${d.n}`).join(" · ")}
          </div>
        )}
      </div>
    );
  }

  const sig = (res.p ?? 1) < 0.05;
  const plotBase = { experiment_id: req.experiment_id, condition_ids: req.condition_ids, signal: req.signal, unit: req.unit };

  return (
    <div className="glass p-4 space-y-3">
      {/* verdict */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full px-2 py-0.5 text-[10px] font-bold"
          style={sig
            ? { background: "color-mix(in srgb, var(--ok) 18%, transparent)", color: "var(--ok)" }
            : { background: "color-mix(in srgb, var(--text-muted) 15%, transparent)", color: "var(--text-muted)" }}>
          {sig ? "SIGNIFICANT" : "N.S."}
        </span>
        <b style={{ color: "var(--text)" }}>{res.test}</b>
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          · {featLabel} of {sigLabel} · {res.design} · {res.normal ? "normal" : "non-normal"}
        </span>
      </div>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        statistic = <b style={{ color: "var(--text)" }}>{fmt(res.statistic, 3)}</b>,
        p = <b style={{ color: "var(--text)" }}>{fmt(res.p, 4)}</b>
        {res.effect_size && <> · {res.effect_size.name} = {fmt(res.effect_size.value, 3)} ({res.effect_size.magnitude})</>}
      </div>
      {res.interpretation && <div className="text-xs" style={{ color: "var(--text-muted)" }}>{res.interpretation}</div>}

      <div className="grid gap-3 md:grid-cols-2">
        {/* plot (server-rendered matplotlib SVG) */}
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
            {featLabel} {sigLabel} by condition · violin + box
          </div>
          <img className="w-full rounded-lg bg-white" alt={`${featLabel} ${sigLabel} by condition`}
            src={analysisApi.plotUrl(plotBase, res.feature, "svg")} />
        </div>

        {/* descriptives + post-hoc */}
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Per condition</div>
          <table className="w-full text-[11px]">
            <thead><tr style={{ color: "var(--text-muted)" }}>
              <th className="text-left">Condition</th><th className="text-right">n</th>
              <th className="text-right">Mean</th><th className="text-right">SD</th><th className="text-right">Normal?</th>
            </tr></thead>
            <tbody>
              {res.descriptives?.map((d) => (
                <tr key={d.condition}>
                  <td style={{ color: "var(--text)" }}>{d.condition}</td>
                  <td className="tnum text-right">{d.n}</td>
                  <td className="tnum text-right">{fmt(d.mean)}</td>
                  <td className="tnum text-right">{fmt(d.sd)}</td>
                  <td className="tnum text-right">
                    {d.shapiro_p == null ? "—" : `${d.shapiro_p > 0.05 ? "✓" : "✗"} ${fmt(d.shapiro_p)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {res.posthoc && res.posthoc.length > 0 && (
            <div className="mt-2 text-[11px]" style={{ color: "var(--text-muted)" }}>
              <div className="text-[10px] uppercase tracking-wide">Post-hoc (Holm)</div>
              {res.posthoc.map((ph, i) => (
                <div key={i}>{ph.a} vs {ph.b}: p={fmt(ph.p_corr)} {ph.sig ? "✓" : ""}</div>
              ))}
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <a className="chip-dl" href={analysisApi.plotUrl(plotBase, res.feature, "svg")}>⬇ SVG</a>
            <a className="chip-dl" href={analysisApi.plotUrl(plotBase, res.feature, "pdf")}>⬇ PDF</a>
            <button className="chip-dl" onClick={() => downloadCsv(res)}>⬇ values CSV</button>
            <button className="chip-dl" onClick={() => downloadJson(res)}>⬇ JSON</button>
          </div>
        </div>
      </div>
    </div>
  );
}
