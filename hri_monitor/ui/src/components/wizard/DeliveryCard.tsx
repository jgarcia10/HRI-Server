/**
 * Delivery card: the three live settings that shape how the robot feeds the participant,
 * the mat as the experimenter sees it, and the way out of a blocked delivery.
 *
 * The settings map 1:1 onto the supply profile the hub already exposes
 * (`lookahead` / `side` / `pace`); only the words changed.
 */
import { AlertTriangle, Eraser, HandHelping, Truck } from "lucide-react";
import type { KitTaskState, SupplyState } from "../../lib/kit";
import { MatSpot, PieceName, describePartId } from "./pieces";
import { Banner, Btn, Card, Segmented } from "./ui";
import { SLOTS, type Slot, blockedMessage, findPart, partName, slotWord } from "./vocab";

export function DeliveryCard({
  task,
  supply,
  active,
  error,
  onProfile,
  onAskNext,
  onSlotCleared,
  onMatCleared,
}: {
  task: KitTaskState | null;
  supply: SupplyState | null;
  active: boolean;
  error: string | null;
  onProfile: (patch: { lookahead?: number; side?: string; pace?: string }) => void;
  onAskNext: () => void;
  onSlotCleared: (slot: Slot) => void;
  onMatCleared: () => void;
}) {
  const profile = supply?.profile;
  const lookahead = profile?.lookahead ?? 1;
  const side = profile?.side ?? "C";
  const pace = profile?.pace ?? "normal";
  const nextPart = findPart(task, supply?.next_part_id);
  const onRequest = lookahead === 0;
  const failedPick = supply?.blocked?.reason === "part_failed";
  // Same rule as before: asking only makes sense on request-only mode, or to retry a piece
  // the robot already failed to pick twice.
  const canAsk = active && (onRequest || failedPick);
  const disabledTitle = active ? undefined : "Start a block first";

  return (
    <Card
      icon={Truck}
      title="Delivery settings"
      hint="How the robot feeds pieces to the participant. Changes apply immediately."
      error={error}
    >
      <div className="grid gap-3">
        <Segmented<number>
          label="Pieces ahead"
          helper="0 = only when asked"
          value={lookahead}
          disabled={!active}
          disabledTitle={disabledTitle}
          onChange={(v) => onProfile({ lookahead: v })}
          options={[0, 1, 2, 3].map((n) => ({
            value: n,
            label: String(n),
            sub: n === 0 ? "on request" : n === 1 ? "just-in-time" : `${n} in advance`,
          }))}
        />
        <Segmented<string>
          label="Delivery spot"
          helper="where the robot puts the piece"
          value={side}
          disabled={!active}
          disabledTitle={disabledTitle}
          onChange={(v) => onProfile({ side: v })}
          options={SLOTS.map((s) => ({ value: s as string, label: slotWord(s) }))}
        />
        <Segmented<string>
          label="Robot speed"
          helper="slower feels calmer and safer"
          value={pace}
          disabled={!active}
          disabledTitle={disabledTitle}
          onChange={(v) => onProfile({ pace: v })}
          options={[
            { value: "slow", label: "Slow" },
            { value: "normal", label: "Normal" },
          ]}
        />
      </div>

      <div>
        <p className="mb-1.5 text-[11px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
          On the mat
        </p>
        <div className="grid grid-cols-3 gap-2">
          {SLOTS.map((slot) => (
            <MatSpot
              key={slot}
              slot={slot}
              part={findPart(task, supply?.staged?.[slot])}
              isTarget={slot === side}
            />
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Btn
          variant="primary"
          icon={HandHelping}
          disabled={!canAsk}
          title={
            !active
              ? "Start a block first"
              : canAsk
                ? "Tell the robot to bring the next piece now"
                : "Only needed when Pieces ahead is 0, or to retry a piece the robot could not pick"
          }
          onClick={onAskNext}
        >
          Ask for next piece
        </Btn>
        <span className="text-sm" style={{ color: "var(--text-muted)" }}>
          Next up:{" "}
          {nextPart ? (
            <PieceName part={nextPart} className="font-medium" />
          ) : supply?.next_part_id ? (
            <span className="font-medium">{supply.next_part_id}</span>
          ) : (
            "—"
          )}
        </span>
      </div>

      {supply?.blocked && (
        <Banner tone="warn" icon={AlertTriangle} title="Delivery paused">
          {blockedMessage(
            supply.blocked.reason,
            supply.blocked.needed,
            findPart(task, supply.blocked.needed)
              ? partName(findPart(task, supply.blocked.needed))
              : undefined,
          )}
          <div className="mt-2.5 flex flex-wrap gap-2">
            {SLOTS.map((slot) => (
              <Btn
                key={slot}
                size="sm"
                variant="warn"
                disabled={!active}
                title={
                  active
                    ? `Tell the robot the ${slotWord(slot).toLowerCase()} spot is free again`
                    : "Start a block first"
                }
                onClick={() => onSlotCleared(slot)}
              >
                {slotWord(slot)} spot cleared
              </Btn>
            ))}
            <Btn
              size="sm"
              variant="warn"
              icon={Eraser}
              disabled={!active}
              title={active ? "All three spots are free again" : "Start a block first"}
              onClick={onMatCleared}
            >
              Whole mat cleared
            </Btn>
          </div>
        </Banner>
      )}

      {supply?.failed && supply.failed.length > 0 && (
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Could not be picked:{" "}
          {supply.failed.map((id) => describePartId(findPart(task, id), id)).join(", ")}
        </p>
      )}
    </Card>
  );
}
