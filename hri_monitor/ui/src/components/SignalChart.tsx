import type React from "react";
import type { LucideIcon } from "lucide-react";
import { useId } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import type { Point } from "../lib/ws";

export function SignalChart({
  title, unit, colorVar, icon: Icon, points, value, glow = true,
}: {
  title: string;
  unit: string;
  colorVar: string; // CSS variable name, e.g. "--chart-gsr"
  icon: LucideIcon;
  points: Point[];
  value?: number;
  glow?: boolean; // disable on the highest-rate trace if profiling shows cost
}) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const color = `var(${colorVar})`;

  function GlassTooltip({ active, payload }: { active?: boolean; payload?: Array<{ value: number }> }) {
    if (!active || !payload?.length) return null;
    return (
      <div className="glass" style={{ padding: "4px 10px", borderRadius: "0.6rem" }}>
        <span className="tnum text-sm font-semibold" style={{ color: "var(--text)" }}>
          {payload[0].value.toFixed(2)}{" "}
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>{unit}</span>
        </span>
      </div>
    );
  }

  return (
    <div className="glass p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text-muted)" }}>
          <Icon size={15} style={{ color }} /> {title}
        </h3>
        <span className="tnum text-xl font-semibold">
          {value !== undefined ? value.toFixed(2) : "—"}{" "}
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>{unit}</span>
        </span>
      </div>
      <div
        className={`h-24 ${glow ? "chart-glow" : ""}`}
        style={{ "--glow-color": color } as React.CSSProperties}
      >
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--glass-border)" strokeDasharray="3 3" vertical={false} />
            <YAxis domain={["auto", "auto"]} hide />
            <Area
              type="monotone"
              dataKey="v"
              stroke={color}
              strokeWidth={2}
              fill={`url(#${id})`}
              dot={false}
              isAnimationActive={false}
            />
            <Tooltip
              content={<GlassTooltip />}
              cursor={{ stroke: color, strokeWidth: 1, strokeOpacity: 0.4 }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
