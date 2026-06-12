const STYLES: Record<string, { color: string; pulse?: boolean }> = {
  connected: { color: "var(--ok)", pulse: true },
  connecting: { color: "var(--warn)" },
  reconnecting: { color: "var(--warn)" },
  disabled: { color: "var(--text-muted)" },
};

/** Translucent solid (no blur — spec: small elements skip backdrop-filter). */
export function StatusChip({ name, status }: { name: string; status: string }) {
  const s = STYLES[status] ?? STYLES.disabled;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium"
      style={{ color: s.color, background: `color-mix(in srgb, ${s.color} 12%, transparent)` }}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          s.pulse ? "motion-safe:animate-[pulse-dot_2s_ease-in-out_infinite]" : ""
        }`}
        style={{ background: s.color, boxShadow: `0 0 6px ${s.color}` }}
      />
      {name} · {status}
    </span>
  );
}
