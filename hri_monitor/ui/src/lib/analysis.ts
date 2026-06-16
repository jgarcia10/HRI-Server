import { useCallback, useEffect, useState } from "react";

export type EffectSize = { name: string; value: number; magnitude: string };
export type Descriptive = { condition: string; n: number; mean?: number; sd?: number; shapiro_p?: number | null };
export type PostHoc = { a: string; b: string; p_corr: number; sig: boolean };
export type ValueRow = { condition: string; subject: number; value: number };
export type AnalysisResult = {
  ok: boolean;
  feature: string;
  signal?: string;
  unit?: string;
  reason?: string;                 // when ok === false
  test?: string;
  design?: "paired" | "unpaired";
  normal?: boolean;
  statistic?: number;
  p?: number;
  effect_size?: EffectSize;
  descriptives?: Descriptive[];
  posthoc?: PostHoc[];
  values?: ValueRow[];
  interpretation?: string;
};
export type AnalysisOptions = {
  signals: string[];
  features: string[];
  conditions: { id: number; name: string }[];
};
export type CompareReq = {
  experiment_id: number;
  condition_ids: number[];
  signal: string;
  features: string[];
  unit: "participant" | "recording";
};

export const SIGNAL_LABELS: Record<string, string> = {
  "shimmer.gsr": "GSR (µS)", "shimmer.ppg": "PPG (mV)", "ppg.hr": "HR (bpm)",
  "ppg.hrv": "HRV (ms)", "rgb.blink": "Blink (/min)",
  "thermal.forehead": "Forehead (°C)", "thermal.left_cheek": "L cheek (°C)",
  "thermal.right_cheek": "R cheek (°C)", "thermal.nose": "Nose (°C)",
};
export const FEATURE_LABELS: Record<string, string> = {
  mean: "Mean", sd: "SD", min: "Min", max: "Max", slope: "Slope", peaks_per_min: "Peaks/min",
};

async function j<T>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(url, opts);
  return r.json();
}

export const analysisApi = {
  options: (expId: number) => j<AnalysisOptions>(`/api/experiments/${expId}/analysis/options`),
  compare: (req: CompareReq) =>
    j<{ results: AnalysisResult[] }>("/api/analysis/compare", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req),
    }),
  // plot download URL (used as <a href> so the browser saves the file)
  plotUrl: (req: Omit<CompareReq, "features">, feature: string, format: "svg" | "pdf") => {
    const p = new URLSearchParams();
    p.set("experiment_id", String(req.experiment_id));
    req.condition_ids.forEach((c) => p.append("condition_ids", String(c)));
    p.set("signal", req.signal); p.set("feature", feature);
    p.set("unit", req.unit); p.set("format", format);
    return `/api/analysis/plot?${p.toString()}`;
  },
};

export function useAnalysisOptions(expId: number | null) {
  const [options, setOptions] = useState<AnalysisOptions | null>(null);
  const refresh = useCallback(async () => {
    if (expId == null) { setOptions(null); return; }
    setOptions(await analysisApi.options(expId));
  }, [expId]);
  useEffect(() => { refresh(); }, [refresh]);
  return options;
}
