/** What the participant is building right now, and which brick they need next. */
import { Blocks, MapPin, Timer } from "lucide-react";
import type { KitTaskState, SupplyState } from "../../lib/kit";
import { PieceChip, PieceTrack } from "./pieces";
import { Card, Pill } from "./ui";
import { clock, figureCount, figureKindWord, slotWord } from "./vocab";

export function NowBuildingCard({
  task,
  supply,
}: {
  task: KitTaskState | null;
  supply: SupplyState | null;
}) {
  const running = task !== null && task.phase !== "idle";
  const part = task?.current_part ?? null;
  const total = figureCount(task);
  const stagedSlot =
    part && supply?.staged
      ? (Object.entries(supply.staged).find(([, id]) => id === part.id)?.[0] ?? null)
      : null;
  const timeLeft = clock(task?.remaining_s);
  const kind = figureKindWord(task?.kind);

  return (
    <Card
      icon={Blocks}
      title="Now building"
      hint="The figure on the participant's mat."
      right={
        timeLeft ? (
          <Pill tone={(task?.remaining_s ?? 99) < 30 ? "err" : "warn"} icon={Timer}
                title="Time left for this figure">
            {timeLeft} left
          </Pill>
        ) : undefined
      }
    >
      {!running ? (
        <p className="py-6 text-center text-sm" style={{ color: "var(--text-muted)" }}>
          No block running. Start one in <b>Session</b>.
        </p>
      ) : task?.phase === "between_orders" ? (
        <div className="py-4">
          <p className="text-lg font-semibold">Between figures</p>
          <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
            Clear the mat, then press <b>Next figure</b> when the participant is ready.
          </p>
        </div>
      ) : task?.phase === "done" ? (
        <div className="py-4">
          <p className="text-lg font-semibold">Block finished</p>
          <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
            All {total} figures done. Press <b>Stop block</b> to close the recording.
          </p>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-2xl font-semibold leading-tight">
              {task?.order_name ?? task?.order_id ?? "Figure"}
            </span>
            <span className="text-sm" style={{ color: "var(--text-muted)" }}>
              figure {(task?.order_index ?? 0) + 1} of {total || "?"}
              {kind ? ` · ${kind}` : ""}
            </span>
          </div>

          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Piece <b style={{ color: "var(--text)" }}>{(task?.step_index ?? 0) + 1}</b> of{" "}
            {task?.n_parts ?? 0}
          </p>

          {part ? (
            <PieceChip
              part={part}
              glyphSize={38}
              note={
                stagedSlot
                  ? undefined
                  : "not on the mat yet — the robot is bringing it"
              }
            />
          ) : (
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              Waiting for the next piece…
            </p>
          )}

          {stagedSlot && (
            <Pill tone="ok" icon={MapPin} className="self-start"
                  title="Where this piece is waiting on the mat">
              On the mat: {slotWord(stagedSlot)}
            </Pill>
          )}

          {task && task.parts?.length > 0 && (
            <div>
              <p className="mb-1.5 text-[11px] uppercase tracking-wider"
                 style={{ color: "var(--text-muted)" }}>
                Assembly order
              </p>
              <PieceTrack parts={task.parts} stepIndex={task.step_index} />
            </div>
          )}
        </>
      )}
    </Card>
  );
}
