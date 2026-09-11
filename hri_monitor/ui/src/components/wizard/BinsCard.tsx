/**
 * How to load the bins for the figure on the table right now.
 *
 * The depot is a 5 × 3 grid: one column per colour, three rows going away from the robot.
 * The mat sits beyond the depot, so the arm carrying a brick out to the mat passes over the
 * rows in front of the bin it just emptied — which is why every figure is laid out back row
 * first, and why the operator needs to see *which* bins to fill rather than filling the row
 * nearest the robot out of habit. Row 3 is the one closest to the participant.
 */
import { Package } from "lucide-react";
import type { KitPart, KitTaskState, SupplyState } from "../../lib/kit";
import { ShapeGlyph } from "./pieces";
import { Card } from "./ui";
import { colorHex, partName } from "./vocab";

const COLUMNS = ["RD", "OR", "BL", "SF", "LM"] as const;
const COLUMN_NAME: Record<string, string> = {
  RD: "red",
  OR: "orange",
  BL: "blue",
  SF: "seafoam",
  LM: "lime",
};
const ROWS = [3, 2, 1] as const; // farthest from the robot first — the order they empty in
const ROW_NOTE: Record<number, string> = {
  3: "back row · nearest the participant · emptied first",
  2: "middle row",
  1: "front row · nearest the robot · emptied last",
};

export function BinsCard({
  task,
  supply,
}: {
  task: KitTaskState | null;
  supply: SupplyState | null;
}) {
  const running = task !== null && task.phase !== "idle";
  const parts = task?.parts ?? [];
  const byBin = new Map<string, { part: KitPart; step: number }>();
  parts.forEach((part, i) => byBin.set(part.depot_slot, { part, step: i + 1 }));
  const gone = new Set(supply?.supplied ?? []);
  const filled = parts.length;

  return (
    <Card
      icon={Package}
      title="Load the bins"
      hint={
        running
          ? `${filled} of the 14 bins are used by this figure. Fill only those, and leave the rest empty.`
          : "Which bin holds which piece, once a figure is running."
      }
    >
      {!running ? (
        <p className="py-6 text-center text-sm" style={{ color: "var(--text-muted)" }}>
          Start a block to see the layout.
        </p>
      ) : (
        <div className="grid gap-2">
          <div className="grid grid-cols-[auto_repeat(5,minmax(0,1fr))] gap-1.5 text-[11px]">
            <span />
            {COLUMNS.map((c) => (
              <span
                key={c}
                className="text-center uppercase tracking-wider"
                style={{ color: colorHex(COLUMN_NAME[c]) }}
              >
                {COLUMN_NAME[c]}
              </span>
            ))}
            {ROWS.map((row) => (
              <Row key={row} row={row} byBin={byBin} gone={gone} />
            ))}
          </div>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            The robot empties the back row first so it never carries a piece over the ones
            still waiting. A faded bin has already been delivered.
          </p>
        </div>
      )}
    </Card>
  );
}

function Row({
  row,
  byBin,
  gone,
}: {
  row: number;
  byBin: Map<string, { part: KitPart; step: number }>;
  gone: Set<string>;
}) {
  return (
    <>
      <span
        className="self-center pr-1 text-right leading-tight"
        style={{ color: "var(--text-muted)" }}
        title={ROW_NOTE[row]}
      >
        row {row}
        {row !== 2 && (
          <span className="block opacity-70">{row === 3 ? "back" : "front"}</span>
        )}
      </span>
      {COLUMNS.map((col) => {
        const bin = `${col}${row}`;
        const entry = byBin.get(bin);
        if (!entry) {
          return (
            <div
              key={bin}
              className="rounded-xl border border-dashed py-2 text-center"
              style={{ borderColor: "var(--border)", color: "var(--text-muted)", opacity: 0.5 }}
            >
              empty
            </div>
          );
        }
        const { part, step } = entry;
        const c = colorHex(part.color);
        const delivered = gone.has(part.id);
        return (
          <div
            key={bin}
            className="flex flex-col items-center gap-0.5 rounded-xl px-1 py-1.5"
            title={`${bin}: ${partName(part)} — piece ${step} of the figure`}
            style={{
              background: `color-mix(in srgb, ${c} 14%, transparent)`,
              border: `1px solid color-mix(in srgb, ${c} 45%, transparent)`,
              opacity: delivered ? 0.35 : 1,
            }}
          >
            <ShapeGlyph type={part.type} high={part.high} color={part.color} size={20} />
            <span className="font-semibold tabular-nums">{bin}</span>
            <span style={{ color: "var(--text-muted)" }}>#{step}</span>
          </div>
        );
      })}
    </>
  );
}
