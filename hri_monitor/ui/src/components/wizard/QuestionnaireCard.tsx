/**
 * Post-block questionnaires, seen from the experimenter's side.
 *
 * The participant answers NASA-TLX and the trust scale on their own screen after every block;
 * the hub refuses to open the next block until they are done. So this card exists to answer
 * three questions at a glance: are they still answering, what did they score, and — when a
 * participant cannot or will not answer — how do I get out of it (Skip, with a reason that
 * lands in the database).
 */
import { ClipboardList, Download, SkipForward } from "lucide-react";
import { useState } from "react";
import type { QuestionnaireState } from "../../lib/kit";
import { Btn, Card, Pill, Readout } from "./ui";
import {
  conditionInfo,
  INSTRUMENT_ORDER,
  instrumentRange,
  instrumentWord,
  type Tone,
} from "./vocab";

const score = (v: number | null | undefined) =>
  v === null || v === undefined ? null : v.toFixed(1);

/** "Done ✓ (NASA-TLX 45.8 · Trust 5.8)" and friends — one sentence, no codes. */
function headline(state: QuestionnaireState): { text: string; tone: Tone; live: boolean } {
  if (state.status === "none") {
    return {
      text: "Not started — they open on the participant's screen when you stop a block.",
      tone: "muted",
      live: false,
    };
  }
  if (state.status === "pending") {
    const next = state.next;
    const n = next ? state.order.indexOf(next) + 1 : state.order.length;
    return {
      text: `Participant is answering on their screen — ${
        next ? instrumentWord(next) : "finishing"
      } (${n} of ${state.order.length})`,
      tone: "warn",
      live: true,
    };
  }
  if (state.outcome === "skipped") {
    return { text: "Skipped — no answers were recorded for this block.", tone: "muted", live: false };
  }
  const parts = INSTRUMENT_ORDER.filter((k) => state.done[k] !== undefined).map(
    (k) => `${instrumentWord(k)} ${score(state.done[k])}`,
  );
  return {
    text: `Done ✓${parts.length ? ` (${parts.join(" · ")})` : ""}`,
    tone: "ok",
    live: false,
  };
}

function statusPill(state: QuestionnaireState) {
  if (state.status === "pending") return { tone: "warn" as Tone, label: "Answering now", pulse: true };
  if (state.status === "none") return { tone: "muted" as Tone, label: "Not started", pulse: false };
  return state.outcome === "skipped"
    ? { tone: "muted" as Tone, label: "Skipped", pulse: false }
    : { tone: "ok" as Tone, label: "Done", pulse: false };
}

export function QuestionnaireCard({
  state,
  error,
  onSkip,
}: {
  state: QuestionnaireState;
  error: string | null;
  onSkip: (reason: string) => void;
}) {
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");

  const pending = state.status === "pending";
  const done: Record<string, number> = state.status === "none" ? {} : state.done;
  const head = headline(state);
  const pill = statusPill(state);

  const skip = () => {
    onSkip(reason.trim() || "skipped by wizard");
    setAsking(false);
    setReason("");
  };

  return (
    <Card
      icon={ClipboardList}
      title="Questionnaires"
      hint="Workload and trust, answered by the participant after each block."
      error={error}
      right={
        <Pill
          tone={pill.tone}
          pulse={pill.pulse}
          className="whitespace-nowrap"
          title="Post-block questionnaires"
        >
          {pill.label}
        </Pill>
      }
    >
      <div>
        <p className="text-base font-medium" style={{ color: head.live ? "var(--warn)" : "var(--text)" }}>
          {head.text}
        </p>
        {state.status !== "none" && (
          <p className="mt-0.5 text-xs" style={{ color: "var(--text-muted)" }}>
            for <b style={{ color: "var(--text)" }}>{state.participant}</b> ·{" "}
            {conditionInfo(state.condition).name}
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2">
        {INSTRUMENT_ORDER.map((k) => (
          <Readout
            key={k}
            label={`${instrumentWord(k)} · ${instrumentRange(k)}`}
            tone={done[k] === undefined ? "muted" : "ok"}
            value={score(done[k]) ?? (pending ? "waiting…" : "—")}
          />
        ))}
      </div>

      {pending &&
        (asking ? (
          <div className="flex flex-wrap items-center gap-2">
            <input
              className="min-w-0 flex-1 rounded-xl px-3 py-2 text-sm outline-none"
              style={{
                background: "color-mix(in srgb, var(--text-muted) 8%, transparent)",
                border: "1px solid color-mix(in srgb, var(--text-muted) 22%, transparent)",
                color: "var(--text)",
              }}
              autoFocus
              placeholder="Why? (optional — goes in the logbook)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && skip()}
            />
            <Btn variant="warn" icon={SkipForward} title="Close the questionnaires unanswered" onClick={skip}>
              Confirm skip
            </Btn>
            <Btn variant="quiet" title="Keep waiting for the participant" onClick={() => setAsking(false)}>
              Cancel
            </Btn>
          </div>
        ) : (
          <Btn
            variant="quiet"
            icon={SkipForward}
            className="self-start"
            title="Only if the participant cannot answer — the block is then filed without scores"
            onClick={() => setAsking(true)}
          >
            Skip questionnaires
          </Btn>
        ))}

      <div className="flex flex-wrap items-center gap-3 text-xs" style={{ color: "var(--text-muted)" }}>
        <Download size={13} />
        Export CSV:
        {INSTRUMENT_ORDER.map((k) => (
          <a
            key={k}
            href={`/api/kit/questionnaires/${k}.csv`}
            download
            className="underline underline-offset-2"
            style={{ color: "var(--accent)" }}
            title={`All ${instrumentWord(k)} answers so far, one row per block`}
          >
            {instrumentWord(k)}
          </a>
        ))}
      </div>
    </Card>
  );
}
