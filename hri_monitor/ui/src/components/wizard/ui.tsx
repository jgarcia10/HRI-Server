/**
 * Small Clinical Frost building blocks for the experimenter page.
 *
 * Everything here is theme-token driven (`var(--accent)`, `var(--err)`, …) so the page keeps
 * working in light and dark, and every interactive element carries a `title` so a disabled
 * control can always explain itself.
 */
import type { LucideIcon } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import type { Tone } from "./vocab";

const TONE_VAR: Record<Tone, string> = {
  ok: "var(--ok)",
  warn: "var(--warn)",
  err: "var(--err)",
  muted: "var(--text-muted)",
  accent: "var(--accent)",
};

export const toneColor = (tone: Tone) => TONE_VAR[tone];

/* ------------------------------------------------------------------- card */

export function Card({
  icon: Icon,
  title,
  hint,
  error,
  right,
  children,
  className = "",
}: {
  icon: LucideIcon;
  title: string;
  hint?: ReactNode;
  error?: string | null;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`glass flex flex-col gap-3 p-5 ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider"
              style={{ color: "var(--text-muted)" }}>
            <Icon size={15} /> {title}
          </h3>
          {hint && (
            <p className="mt-1 text-xs" style={{ color: "var(--text-muted)", opacity: 0.85 }}>
              {hint}
            </p>
          )}
        </div>
        {right}
      </div>
      {children}
      {error && <Banner tone="err" icon={AlertTriangle}>{error}</Banner>}
    </section>
  );
}

/* ------------------------------------------------------------------- pill */

export function Pill({
  tone,
  icon: Icon,
  children,
  title,
  pulse = false,
  className = "",
}: {
  tone: Tone;
  icon?: LucideIcon;
  children: ReactNode;
  title?: string;
  pulse?: boolean;
  className?: string;
}) {
  const c = TONE_VAR[tone];
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium ${className}`}
      style={{ color: c, background: `color-mix(in srgb, ${c} 13%, transparent)` }}
    >
      {Icon ? (
        <Icon size={14} />
      ) : (
        <span
          className={`h-2 w-2 shrink-0 rounded-full ${
            pulse ? "motion-safe:animate-[pulse-dot_2s_ease-in-out_infinite]" : ""
          }`}
          style={{ background: c, boxShadow: `0 0 6px ${c}` }}
        />
      )}
      {children}
    </span>
  );
}

/* ----------------------------------------------------------------- banner */

export function Banner({
  tone,
  icon: Icon,
  title,
  children,
}: {
  tone: Tone;
  icon?: LucideIcon;
  title?: string;
  children: ReactNode;
}) {
  const c = TONE_VAR[tone];
  return (
    <div
      className="flex items-start gap-2.5 rounded-xl px-3.5 py-3 text-sm"
      style={{
        color: c,
        background: `color-mix(in srgb, ${c} 12%, transparent)`,
        border: `1px solid color-mix(in srgb, ${c} 35%, transparent)`,
      }}
    >
      {Icon && <Icon size={17} className="mt-px shrink-0" />}
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        <div className={title ? "mt-0.5" : ""}>{children}</div>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- button */

type Variant = "primary" | "neutral" | "quiet" | "go" | "danger" | "warn";
type Size = "sm" | "md" | "lg" | "xl" | "stop";

const SIZE: Record<Size, string> = {
  sm: "px-3 py-1.5 text-[13px] gap-1.5 rounded-lg",
  md: "px-4 py-2.5 text-sm gap-2 rounded-xl",
  lg: "px-5 py-3 text-base gap-2 rounded-xl",
  xl: "px-6 py-5 text-xl font-semibold gap-3 rounded-2xl",
  // The one control that has to be findable without looking: bar-height, wide, unmissable.
  stop: "h-14 px-7 text-lg font-bold tracking-wide gap-2.5 rounded-xl shadow-lg",
};

/**
 * Filled buttons take their text colour from `--base` (the page ground) rather than white:
 * the Clinical Frost accents are dark in the light theme and light in the dark theme, so a
 * hard-coded white would go unreadable at night.
 */
function variantStyle(variant: Variant): CSSProperties {
  switch (variant) {
    case "primary":
      return { background: "var(--accent)", color: "var(--base)" };
    case "go":
      return { background: "var(--ok)", color: "var(--base)" };
    case "danger":
      return { background: "var(--err)", color: "var(--base)" };
    case "warn":
      return { background: "var(--warn)", color: "var(--base)" };
    case "quiet":
      return {
        background: "transparent",
        color: "var(--text)",
        border: "1px solid var(--glass-border)",
      };
    default:
      return {
        background: "color-mix(in srgb, var(--text-muted) 12%, transparent)",
        color: "var(--text)",
        border: "1px solid color-mix(in srgb, var(--text-muted) 22%, transparent)",
      };
  }
}

export function Btn({
  icon: Icon,
  iconSize,
  children,
  onClick,
  disabled,
  title,
  variant = "neutral",
  size = "md",
  className = "",
}: {
  icon?: LucideIcon;
  iconSize?: number;
  children?: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  /** Always set on anything that can be disabled — this is how the page explains itself. */
  title?: string;
  variant?: Variant;
  size?: Size;
  className?: string;
}) {
  // No opacity transition on the disabled state: whether a control is live has to read
  // instantly mid-block (and makes headless screenshots of the page honest).
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`inline-flex items-center justify-center font-medium motion-safe:transition-[filter] hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-40 ${SIZE[size]} ${className}`}
      style={variantStyle(variant)}
    >
      {Icon && <Icon size={iconSize ?? (size === "xl" ? 26 : size === "sm" ? 14 : 17)} />}
      {children}
    </button>
  );
}

/* ------------------------------------------------------- segmented control */

export function Segmented<T extends string | number>({
  label,
  helper,
  value,
  options,
  onChange,
  disabled,
  disabledTitle,
}: {
  label: string;
  helper?: string;
  value: T;
  options: { value: T; label: string; sub?: string }[];
  onChange: (v: T) => void;
  disabled?: boolean;
  disabledTitle?: string;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline gap-2">
        <span className="text-sm font-medium">{label}</span>
        {helper && (
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            {helper}
          </span>
        )}
      </div>
      <div
        role="group"
        aria-label={label}
        title={disabled ? disabledTitle : undefined}
        className="flex gap-1 rounded-xl p-1"
        style={{
          background: "color-mix(in srgb, var(--text-muted) 9%, transparent)",
          border: "1px solid color-mix(in srgb, var(--text-muted) 18%, transparent)",
          opacity: disabled ? 0.45 : 1,
        }}
      >
        {options.map((o) => {
          const on = o.value === value;
          return (
            <button
              key={String(o.value)}
              type="button"
              disabled={disabled}
              aria-pressed={on}
              onClick={() => onChange(o.value)}
              title={disabled ? disabledTitle : o.sub ?? o.label}
              // No colour transition: which option is live must be true the instant it changes.
              className="flex-1 rounded-lg px-3 py-2 text-sm font-medium leading-tight disabled:cursor-not-allowed"
              style={
                on
                  ? { background: "var(--accent)", color: "var(--base)" }
                  : { color: "var(--text-muted)", background: "transparent" }
              }
            >
              {o.label}
              {o.sub && (
                <span className="block text-[10px] font-normal opacity-80">{o.sub}</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ misc */

/** Key-cap badge used to advertise the Space shortcut. */
export function Key({ children }: { children: ReactNode }) {
  return (
    <kbd
      className="rounded-md px-2 py-0.5 text-[11px] font-semibold"
      style={{
        background: "color-mix(in srgb, currentColor 18%, transparent)",
        border: "1px solid color-mix(in srgb, currentColor 35%, transparent)",
        color: "inherit",
      }}
    >
      {children}
    </kbd>
  );
}

export function Field({
  label,
  helper,
  children,
}: {
  label: string;
  helper?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium">{label}</span>
      {children}
      {helper && (
        <span className="mt-1 block text-xs" style={{ color: "var(--text-muted)" }}>
          {helper}
        </span>
      )}
    </label>
  );
}

/** Label / value row used for the robot read-outs. */
export function Readout({
  label,
  value,
  tone = "muted",
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
}) {
  return (
    <div
      className="rounded-xl px-3 py-2"
      style={{ background: "color-mix(in srgb, var(--text-muted) 8%, transparent)" }}
    >
      <div className="text-[11px] uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
        {label}
      </div>
      <div className="mt-0.5 text-sm font-semibold" style={{ color: TONE_VAR[tone] === TONE_VAR.muted ? "var(--text)" : TONE_VAR[tone] }}>
        {value}
      </div>
    </div>
  );
}
