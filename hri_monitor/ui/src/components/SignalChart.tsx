import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";
import type { Point } from "../lib/ws";

export function SignalChart({ title, unit, color, points, value }: {
  title: string;
  unit: string;
  color: string;
  points: Point[];
  value?: number;
}) {
  return (
    <div className="rounded-xl bg-slate-900 border border-slate-800 p-4">
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="text-sm font-medium text-slate-400">{title}</h3>
        <span className="text-xl font-semibold text-slate-100">
          {value !== undefined ? value.toFixed(2) : "—"}{" "}
          <span className="text-xs text-slate-500">{unit}</span>
        </span>
      </div>
      <div className="h-24">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points}>
            <YAxis domain={["auto", "auto"]} hide />
            <Line type="monotone" dataKey="v" stroke={color} dot={false}
                  isAnimationActive={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
