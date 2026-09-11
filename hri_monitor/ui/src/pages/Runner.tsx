/**
 * Kit study — experimenter page.
 *
 * One person runs the whole session from here while sitting next to the arm: they open and
 * close a block, keep an eye on the robot, tune how pieces are delivered, log what the
 * participant does, and type what the participant says. The page is a re-skin of the original
 * wizard — same endpoints, same payloads, same enable/disable rules — with the study codes
 * demoted to secondary labels (see `components/wizard/vocab.ts`) and STOP always one click away.
 */
import { useCallback, useEffect, useState } from "react";
import { DeliveryCard } from "../components/wizard/DeliveryCard";
import { LogCard } from "../components/wizard/LogCard";
import { NowBuildingCard } from "../components/wizard/NowBuildingCard";
import { QuestionnaireCard } from "../components/wizard/QuestionnaireCard";
import { RobotCard } from "../components/wizard/RobotCard";
import { type RunningSession, SessionCard } from "../components/wizard/SessionCard";
import { SpeechCard } from "../components/wizard/SpeechCard";
import { TopBar } from "../components/wizard/TopBar";
import type { ConditionCode, Slot } from "../components/wizard/vocab";
import {
  fetchPlan,
  matCleared,
  postEvent,
  type Plan,
  robotCloseGripper,
  robotConnect,
  robotHome,
  robotOpenGripper,
  robotResetGripper,
  robotStop,
  setSupplyProfile,
  skipQuestionnaires,
  startSession,
  stopSession,
  useKitWs,
} from "../lib/kit";

/** Which card shows an error — failures are reported where they were caused, never globally. */
type CardId = "session" | "robot" | "delivery" | "log" | "speech" | "questionnaire";

export function Runner() {
  const { task, robot, supply, questionnaire, connected } = useKitWs();
  const [participant, setParticipant] = useState("P01");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [blockNo, setBlockNo] = useState<1 | 2>(1);
  const [condition, setCondition] = useState<ConditionCode>("C0");
  const [errors, setErrors] = useState<Partial<Record<CardId, string>>>({});
  const [saidLines, setSaidLines] = useState<string[]>([]);
  const [running, setRunning] = useState<RunningSession>(null);

  const run = useCallback(
    (card: CardId, fn: () => Promise<unknown>, after?: () => void) => {
      fn()
        .then(() => {
          setErrors((e) => ({ ...e, [card]: undefined }));
          after?.();
        })
        .catch((e) => setErrors((prev) => ({ ...prev, [card]: String(e?.message ?? e) })));
    },
    [],
  );

  // Who the hub is recording. The websocket only carries task/robot/supply, so the identity
  // of a session started before this tab opened (or from another laptop) has to be polled.
  // Read-only: no new endpoint, just the same /api/kit/state the hook already seeds from.
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fetch("/api/kit/state")
        .then((r) => r.json())
        .then((d) => {
          if (cancelled) return;
          const s = d?.session;
          setRunning(
            s
              ? {
                  participant: String(s.participant ?? ""),
                  condition: String(s.condition ?? ""),
                  block: String(s.block ?? ""),
                }
              : null,
          );
        })
        .catch(() => {});
    load();
    const timer = setInterval(load, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [task?.phase]);

  // Keep the card describing the person actually being recorded (the field is disabled while
  // a block runs, so this can never fight with typing).
  useEffect(() => {
    if (running?.participant && running.participant !== participant) {
      setParticipant(running.participant);
    }
  }, [running?.participant]); // eslint-disable-line react-hooks/exhaustive-deps

  // Counterbalancing: the participant code decides the group (condition order × kit set
  // of block 1). The wizard picks block 1 or 2; condition + orders file follow the plan,
  // but the condition stays editable as an explicit override.
  useEffect(() => {
    if (!participant) return;
    fetchPlan(participant).then(setPlan).catch(() => setPlan(null));
  }, [participant]);
  const planned = plan?.blocks[blockNo - 1] ?? null;
  useEffect(() => {
    if (planned) setCondition(planned.condition);
  }, [planned?.condition, planned]);

  // "active" tracks whether a session/recording exists (any phase but idle) — this is
  // what gates Start/Stop and the wizard controls. "done" still has an active session
  // (Stop must remain enabled) until session.stop() tears it down and the engine
  // publishes a fresh idle task.state.
  const active = task !== null && task.phase !== "idle";
  const canPlace = active && task?.phase === "running";
  // The hub answers session/start with a 409 while the previous block's questionnaires are
  // open, so Start is greyed out (and says why) instead of failing on the click.
  const questionnairesPending = questionnaire.status === "pending";

  const logPiecePlaced = useCallback(
    () => run("log", () => postEvent("part_placed")),
    [run],
  );

  // Space logs a placed piece — the single most-pressed action of a block. Typing anywhere,
  // or a focused button (which the browser already activates with Space), keeps its own Space.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code !== "Space" && e.key !== " ") return;
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || tag === "BUTTON") return;
      if (el?.isContentEditable) return;
      if (!canPlace) return;
      e.preventDefault();
      logPiecePlaced();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [canPlace, logPiecePlaced]);

  const sendSpeech = (text: string) =>
    run("speech", () => postEvent("speech", { text }), () =>
      setSaidLines((prev) => [text, ...prev].slice(0, 6)),
    );

  return (
    <div className="space-y-4">
      <TopBar
        task={task}
        robot={robot}
        connected={connected}
        onStop={() => run("robot", robotStop)}
      />

      {/*
        Two columns from 1100px of *card area* (container query, so the sidebar is already
        discounted), one below. The column wrappers are `display: contents` while narrow, so
        the seven cards stay direct grid items there and the `order-*` utilities give the
        single-column reading order; wide, each wrapper becomes its own stacked column and
        the cards keep their relative order inside it — no ragged gaps between rows.
      */}
      <div className="@container">
        <div className="grid grid-cols-1 items-start gap-4 @min-[1100px]:grid-cols-2">
          {/* left column: set up the block, keep the robot healthy, log what you see */}
          <div className="contents @min-[1100px]:flex @min-[1100px]:flex-col @min-[1100px]:gap-4">
            <div className="order-1">
              <SessionCard
                participant={participant}
                onParticipant={setParticipant}
                plan={plan}
                blockNo={blockNo}
                onBlockNo={setBlockNo}
                condition={condition}
                onCondition={setCondition}
                active={active}
                running={running}
                questionnairesPending={questionnairesPending}
                error={errors.session ?? null}
                onStart={() =>
                  run("session", () =>
                    startSession({
                      participant_code: participant,
                      condition,
                      block: planned?.orders,
                    }),
                  )
                }
                onStop={() =>
                  run("session", stopSession, () => {
                    if (blockNo === 1) setBlockNo(2);
                  })
                }
              />
            </div>
            <div className="order-3">
              <QuestionnaireCard
                state={questionnaire}
                error={errors.questionnaire ?? null}
                onSkip={(reason) => run("questionnaire", () => skipQuestionnaires(reason))}
              />
            </div>
            <div className="order-5">
              <RobotCard
                robot={robot}
                supply={supply}
                error={errors.robot ?? null}
                onHome={() => run("robot", robotHome)}
                onOpenGripper={() => run("robot", robotOpenGripper)}
                onCloseGripper={() => run("robot", robotCloseGripper)}
                onResetGripper={() => run("robot", robotResetGripper)}
                onReconnect={() => run("robot", robotConnect)}
              />
            </div>
            <div className="order-7">
              <LogCard
                task={task}
                active={active}
                error={errors.log ?? null}
                onPiecePlaced={logPiecePlaced}
                onNextFigure={() => run("log", () => postEvent("next_order"))}
                onMatCleared={() => run("log", matCleared)}
                onMoved={(slot: Slot) => run("log", () => postEvent("reposition", { slot }))}
              />
            </div>
          </div>

          {/* right column: what is happening in front of the participant */}
          <div className="contents @min-[1100px]:flex @min-[1100px]:flex-col @min-[1100px]:gap-4">
            <div className="order-2">
              <NowBuildingCard task={task} supply={supply} />
            </div>
            <div className="order-4">
              <DeliveryCard
                task={task}
                supply={supply}
                active={active}
                error={errors.delivery ?? null}
                onProfile={(patch) => run("delivery", () => setSupplyProfile(patch))}
                onAskNext={() => run("delivery", () => postEvent("request_part"))}
                onSlotCleared={(slot: Slot) =>
                  run("delivery", () => postEvent("slot_cleared", { slot }))
                }
                onMatCleared={() => run("delivery", matCleared)}
              />
            </div>
            <div className="order-6">
              <SpeechCard
                active={active}
                error={errors.speech ?? null}
                sent={saidLines}
                onSend={sendSpeech}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
