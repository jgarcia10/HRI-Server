const COLORS: Record<string, string> = {
  connected: "bg-emerald-500/15 text-emerald-400",
  connecting: "bg-amber-500/15 text-amber-400",
  reconnecting: "bg-amber-500/15 text-amber-400",
  disabled: "bg-slate-500/15 text-slate-400",
};

export function StatusChip({ name, status }: { name: string; status: string }) {
  return (
    <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${COLORS[status] ?? COLORS.disabled}`}>
      ● {name} · {status}
    </span>
  );
}
