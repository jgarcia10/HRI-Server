/**
 * How a brick is drawn on the experimenter page: a colour swatch plus a shape glyph, so the
 * piece can be matched against the table at a glance without reading a part id.
 */
import type { KitPart } from "../../lib/kit";
import { colorHex, partName, slotWord } from "./vocab";

/* ------------------------------------------------------------------ glyphs */

/** Toy-brick silhouettes (long / small / roof) drawn in the brick's own colour. */
export function ShapeGlyph({
  type,
  high,
  color,
  size = 28,
}: {
  type: string;
  high?: "left" | "right" | null;
  color: string;
  size?: number;
}) {
  const fill = colorHex(color);
  const w = (size / 26) * 44;
  const common = { fill, stroke: "rgba(0,0,0,0.18)", strokeWidth: 1 };
  return (
    <svg width={w} height={size} viewBox="0 0 44 26" aria-hidden="true" className="shrink-0">
      {type === "1x2" && (
        <>
          <rect x={8} y={3} width={9} height={6} rx={2} {...common} opacity={0.8} />
          <rect x={27} y={3} width={9} height={6} rx={2} {...common} opacity={0.8} />
          <rect x={2} y={8} width={40} height={16} rx={2.5} {...common} />
        </>
      )}
      {type === "1x1" && (
        <>
          <rect x={17.5} y={3} width={9} height={6} rx={2} {...common} opacity={0.8} />
          <rect x={13} y={8} width={18} height={16} rx={2.5} {...common} />
        </>
      )}
      {type === "slope" && (
        <>
          <rect
            x={high === "right" ? 24 : 14}
            y={3}
            width={7}
            height={6}
            rx={2}
            {...common}
            opacity={0.8}
          />
          <polygon
            points={
              high === "right"
                ? "31,24 31,9 23,9 12,19 12,24"
                : "13,24 13,9 21,9 32,19 32,24"
            }
            {...common}
          />
        </>
      )}
      {type !== "1x2" && type !== "1x1" && type !== "slope" && (
        <rect x={10} y={8} width={24} height={16} rx={2.5} {...common} />
      )}
    </svg>
  );
}

export function ColorDot({ color, size = 12 }: { color: string; size?: number }) {
  return (
    <span
      className="inline-block shrink-0 rounded-full"
      style={{
        width: size,
        height: size,
        background: colorHex(color),
        boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.15)",
      }}
    />
  );
}

/* ------------------------------------------------------------------- chips */

/** Inline "● red long brick" used in sentences and lists. */
export function PieceName({ part, className = "" }: { part: KitPart | null; className?: string }) {
  if (!part) {
    return (
      <span className={className} style={{ color: "var(--text-muted)" }}>
        —
      </span>
    );
  }
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <ColorDot color={part.color} />
      {partName(part)}
    </span>
  );
}

/** The hero chip for the piece the participant needs right now. */
export function PieceChip({
  part,
  glyphSize = 34,
  note,
}: {
  part: KitPart;
  glyphSize?: number;
  note?: string;
}) {
  const c = colorHex(part.color);
  return (
    <div
      className="flex items-center gap-3 rounded-2xl px-4 py-3"
      style={{
        background: `color-mix(in srgb, ${c} 14%, transparent)`,
        border: `1px solid color-mix(in srgb, ${c} 45%, transparent)`,
      }}
    >
      <ShapeGlyph type={part.type} high={part.high} color={part.color} size={glyphSize} />
      <div className="min-w-0">
        <div className="text-lg font-semibold leading-tight first-letter:uppercase">
          {partName(part)}
        </div>
        {note && (
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            {note}
          </div>
        )}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- mat spots */

/** One of the three delivery spots on the mat, as the experimenter sees it from above. */
export function MatSpot({
  slot,
  part,
  isTarget,
}: {
  slot: string;
  part: KitPart | null;
  isTarget: boolean;
}) {
  const c = part ? colorHex(part.color) : null;
  return (
    <div
      className="flex min-h-[104px] flex-col items-center justify-center gap-1.5 rounded-2xl px-2 py-3 text-center"
      style={{
        background: c
          ? `color-mix(in srgb, ${c} 13%, transparent)`
          : "color-mix(in srgb, var(--text-muted) 7%, transparent)",
        border: c
          ? `1px solid color-mix(in srgb, ${c} 45%, transparent)`
          : isTarget
            ? "1px dashed color-mix(in srgb, var(--accent) 55%, transparent)"
            : "1px dashed color-mix(in srgb, var(--text-muted) 30%, transparent)",
      }}
    >
      <div
        className="text-[11px] font-semibold uppercase tracking-wider"
        style={{ color: isTarget ? "var(--accent)" : "var(--text-muted)" }}
      >
        {slotWord(slot)}
        {isTarget && " · next"}
      </div>
      {part ? (
        <>
          <ShapeGlyph type={part.type} high={part.high} color={part.color} size={26} />
          <div className="text-xs font-medium leading-tight first-letter:uppercase">
            {partName(part)}
          </div>
        </>
      ) : (
        <div className="text-xs" style={{ color: "var(--text-muted)", opacity: 0.8 }}>
          empty
        </div>
      )}
    </div>
  );
}

/** Row of every piece in the current figure — done, current, still to come. */
export function PieceTrack({ parts, stepIndex }: { parts: KitPart[]; stepIndex: number }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {parts.map((p, i) => {
        const done = i < stepIndex;
        const now = i === stepIndex;
        return (
          <span
            key={p.id}
            title={`${i + 1}. ${partName(p)}${done ? " (placed)" : now ? " (now)" : ""}`}
            className="inline-flex items-center rounded-lg px-1.5 py-1"
            style={{
              background: now ? "color-mix(in srgb, var(--accent) 16%, transparent)" : "transparent",
              border: now
                ? "1px solid color-mix(in srgb, var(--accent) 45%, transparent)"
                : "1px solid transparent",
              opacity: done ? 0.3 : 1,
            }}
          >
            <ShapeGlyph type={p.type} high={p.high} color={p.color} size={16} />
          </span>
        );
      })}
    </div>
  );
}

/** Used by the "could not pick" note, where sometimes only the id survives. */
export const describePartId = (part: KitPart | null, id: string) =>
  part ? partName(part) : `piece ${id}`;
