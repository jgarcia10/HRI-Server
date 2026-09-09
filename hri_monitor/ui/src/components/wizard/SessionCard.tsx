/**
 * Session card: who is sitting down, which half of the study they are in, and the two buttons
 * that open and close a recording.
 *
 * The participant code decides the counterbalancing group (condition order × kit set of the
 * first block). The experimenter picks block 1 or 2; condition and orders file follow the
 * plan, but the condition stays editable as an explicit, visibly-flagged override.
 */
import { AlertTriangle, ArrowRight, CircleStop, Play, Radio, UserRound } from "lucide-react";
import type { Plan } from "../../lib/kit";
import { Banner, Btn, Card, Field, Pill, Segmented } from "./ui";
import { CONDITIONS, type ConditionCode, conditionInfo, familyWord } from "./vocab";

/** Who the hub is actually recording right now (it may predate this browser tab). */
export type RunningSession = {
  participant: string;
  condition: string;
  block: string;
} | null;

function planSentence(plan: Plan | null): string {
  if (!plan || plan.blocks.length < 2) return "Type a participant code to see the plan.";
  return plan.blocks
    .map(
      (b) =>
        `Block ${b.block}: ${conditionInfo(b.condition).name} · ${familyWord(b.family)}`,
    )
    .join("  →  ");
}

export function SessionCard({
  participant,
  onParticipant,
  plan,
  blockNo,
  onBlockNo,
  condition,
  onCondition,
  active,
  running,
  error,
  onStart,
  onStop,
}: {
  participant: string;
  onParticipant: (v: string) => void;
  plan: Plan | null;
  blockNo: 1 | 2;
  onBlockNo: (v: 1 | 2) => void;
  condition: ConditionCode;
  onCondition: (v: ConditionCode) => void;
  active: boolean;
  running: RunningSession;
  error: string | null;
  onStart: () => void;
  onStop: () => void;
}) {
  const planned = plan?.blocks[blockNo - 1] ?? null;
  const overridden = planned !== null && planned.condition !== condition;
  const chosen = conditionInfo(condition);

  return (
    <Card
      icon={UserRound}
      title="Session"
      hint="Start and stop one block of the study."
      error={error}
      right={
        active && running ? (
          <Pill tone="err" icon={Radio} title="A block is being recorded right now">
            Recording {running.participant}
          </Pill>
        ) : undefined
      }
    >
      {active && running && (
        <p className="-mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
          Running now: <b style={{ color: "var(--text)" }}>{running.participant}</b> ·{" "}
          {conditionInfo(running.condition).name} · {familyWord(running.block)}
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <Field label="Participant code" helper="Sets the order of the two blocks automatically">
          <input
            className="w-full rounded-xl px-3 py-2 text-base outline-none"
            style={{
              background: "color-mix(in srgb, var(--text-muted) 8%, transparent)",
              border: "1px solid color-mix(in srgb, var(--text-muted) 22%, transparent)",
              color: "var(--text)",
            }}
            value={participant}
            disabled={active}
            title={active ? "Stop the block before changing the participant" : undefined}
            onChange={(e) => onParticipant(e.target.value)}
          />
        </Field>

        <Segmented<1 | 2>
          label="Which block"
          helper="first or second half"
          value={blockNo}
          disabled={active}
          disabledTitle="Stop the block before switching"
          onChange={onBlockNo}
          options={[
            { value: 1, label: "Block 1", sub: "first" },
            { value: 2, label: "Block 2", sub: "second" },
          ]}
        />
      </div>

      <div
        className="rounded-xl px-3.5 py-3"
        style={{ background: "color-mix(in srgb, var(--accent) 8%, transparent)" }}
      >
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider"
             style={{ color: "var(--text-muted)" }}>
          Automatic plan {plan && <span>· group {plan.group} of 4</span>}
        </div>
        <p className="mt-1 flex flex-wrap items-center gap-1.5 text-sm font-medium">
          {plan && plan.blocks.length >= 2 ? (
            plan.blocks.map((b, i) => (
              <span key={b.block} className="inline-flex items-center gap-1.5">
                {i > 0 && <ArrowRight size={14} style={{ color: "var(--text-muted)" }} />}
                <span style={{ opacity: b.block === blockNo ? 1 : 0.55 }}>
                  Block {b.block}: {conditionInfo(b.condition).name} · {familyWord(b.family)}
                </span>
              </span>
            ))
          ) : (
            <span style={{ color: "var(--text-muted)" }}>{planSentence(plan)}</span>
          )}
        </p>
        {planned && (
          <p className="mt-1 font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>
            this block: {planned.condition} · {planned.family} · {planned.orders}
          </p>
        )}
      </div>

      <Segmented<ConditionCode>
        label="Assistant for this block"
        helper="follows the plan unless you override it"
        value={condition}
        disabled={active}
        disabledTitle="Stop the block before changing the assistant"
        onChange={onCondition}
        options={CONDITIONS.map((c) => ({ value: c.code, label: c.name, sub: c.detail }))}
      />
      <p className="-mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
        {chosen.blurb}
      </p>

      {overridden && planned && (
        <Banner tone="warn" icon={AlertTriangle} title="Override">
          The plan says {conditionInfo(planned.condition).name} for block {blockNo}; you picked{" "}
          {chosen.name}. Note it in the logbook.
        </Banner>
      )}

      <div className="mt-1 flex flex-wrap gap-2">
        <Btn
          variant="go"
          size="lg"
          icon={Play}
          disabled={active}
          title={active ? "A block is already running — stop it first" : `Start block ${blockNo}`}
          onClick={onStart}
        >
          Start block {blockNo}
        </Btn>
        <Btn
          variant="quiet"
          size="lg"
          icon={CircleStop}
          disabled={!active}
          title={!active ? "No block is running" : "End this block and close the recording"}
          onClick={onStop}
        >
          Stop block
        </Btn>
      </div>
    </Card>
  );
}
