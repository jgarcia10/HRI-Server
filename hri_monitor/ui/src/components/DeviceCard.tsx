import type React from "react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { StatusChip } from "./StatusChip";

export function DeviceCard({
  name, icon: Icon, status, simulate, busy, onToggleSim, onRestart, onDisconnect, children,
}: {
  name: string;
  icon: LucideIcon;
  status: string;
  simulate: boolean;
  busy?: boolean;
  onToggleSim: (sim: boolean) => void;
  onRestart: () => void;
  onDisconnect: () => void;
  children: ReactNode;
}) {
  return (
    <div className="glass p-4">
      <div className="mb-3 flex items-center gap-2">
        <Icon size={16} style={{ color: "var(--accent)" }} />
        <b className="text-sm" style={{ color: "var(--text)" }}>{name}</b>
        <span className="ml-auto"><StatusChip name="" status={busy ? "connecting" : status} /></span>
      </div>
      <div className="space-y-2 text-sm">{children}</div>
      <div className="mt-3 flex items-center gap-2">
        <button onClick={onRestart} disabled={busy}
          className="rounded-lg px-3 py-1.5 text-xs font-semibold"
          style={{ color: "var(--accent)", background: "color-mix(in srgb, var(--accent) 12%, transparent)" }}>
          Restart
        </button>
        <button onClick={onDisconnect} disabled={busy}
          className="rounded-lg border px-3 py-1.5 text-xs"
          style={{ color: "var(--text-muted)", borderColor: "var(--glass-border)" }}>
          Disconnect
        </button>
        <label className="ml-auto flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
          {simulate ? "Simulator" : "Real"}
          <input type="checkbox" checked={!simulate} onChange={(e) => onToggleSim(!e.target.checked)} />
        </label>
      </div>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 shrink-0 text-xs" style={{ color: "var(--text-muted)" }}>{label}</span>
      <div className="flex-1">{children}</div>
    </div>
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props}
      className="w-full rounded-lg border px-2 py-1 text-xs"
      style={{ borderColor: "var(--glass-border)", background: "var(--glass-bg)", color: "var(--text)" }} />
  );
}
