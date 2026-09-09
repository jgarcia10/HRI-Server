/**
 * The four things the experimenter logs while watching the participant. "Piece placed" is the
 * one pressed dozens of times per block, so it gets the whole width and the Space bar.
 */
import { CheckCircle2, Eraser, ListChecks, Move, SkipForward } from "lucide-react";
import type { KitTaskState } from "../../lib/kit";
import { Btn, Card, Key } from "./ui";
import { SLOTS, type Slot, slotWord } from "./vocab";

export function LogCard({
  task,
  active,
  error,
  onPiecePlaced,
  onNextFigure,
  onMatCleared,
  onMoved,
}: {
  task: KitTaskState | null;
  active: boolean;
  error: string | null;
  onPiecePlaced: () => void;
  onNextFigure: () => void;
  onMatCleared: () => void;
  onMoved: (slot: Slot) => void;
}) {
  const running = active && task?.phase === "running";
  const between = task?.phase === "between_orders";
  return (
    <Card
      icon={ListChecks}
      title="Log what happened"
      hint="Every press is timestamped into the recording."
      error={error}
    >
      <Btn
        variant="primary"
        size="xl"
        icon={CheckCircle2}
        disabled={!running}
        title={
          running
            ? "The participant just clicked the current piece into place (Space)"
            : active
              ? "Only while a figure is being built"
              : "Start a block first"
        }
        onClick={onPiecePlaced}
        className="w-full"
      >
        Piece placed
        <Key>Space</Key>
      </Btn>

      <div className="flex flex-wrap gap-2">
        <Btn
          variant={between ? "go" : "neutral"}
          icon={SkipForward}
          disabled={!between}
          title={
            between
              ? "Move on to the next figure"
              : "Available once the current figure is finished"
          }
          onClick={onNextFigure}
        >
          Next figure
        </Btn>
        <Btn
          variant="neutral"
          icon={Eraser}
          disabled={!active}
          title={active ? "The mat is empty again" : "Start a block first"}
          onClick={onMatCleared}
        >
          Mat cleared
        </Btn>
      </div>

      <div>
        <p className="mb-1.5 flex items-center gap-1.5 text-sm font-medium">
          <Move size={15} style={{ color: "var(--text-muted)" }} />
          Participant moved a piece to…
        </p>
        <div className="grid grid-cols-3 gap-2">
          {SLOTS.map((slot) => (
            <Btn
              key={slot}
              variant="neutral"
              disabled={!active}
              title={
                active
                  ? `The participant moved a piece to the ${slotWord(slot).toLowerCase()} spot`
                  : "Start a block first"
              }
              onClick={() => onMoved(slot)}
            >
              {slotWord(slot)}
            </Btn>
          ))}
        </div>
      </div>
    </Card>
  );
}
