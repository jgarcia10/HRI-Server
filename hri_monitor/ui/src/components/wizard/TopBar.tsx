/**
 * Sticky status bar: where the session is, what the robot is doing, and the one control that
 * must never be more than a click away.
 */
import { Bot, ClipboardList, Octagon, WifiOff } from "lucide-react";
import type { KitTaskState, RobotState } from "../../lib/kit";
import { Btn, Pill } from "./ui";
import { robotStatusWord, sessionHeadline } from "./vocab";

export function TopBar({
  task,
  robot,
  connected,
  onStop,
}: {
  task: KitTaskState | null;
  robot: RobotState | null;
  connected: boolean;
  onStop: () => void;
}) {
  const session = sessionHeadline(task);
  const robotStatus = robotStatusWord(robot);
  return (
    <header className="glass sticky top-0 z-30 flex flex-wrap items-center gap-3 px-4 py-3">
      <div className="mr-1 min-w-0">
        <h2 className="text-base font-semibold leading-tight">Kit study</h2>
        <p className="text-[11px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          experimenter
        </p>
      </div>

      <Pill tone={session.tone} icon={ClipboardList} title="Where the participant is in the block">
        {session.text}
      </Pill>

      <Pill
        tone={robotStatus.tone}
        icon={Bot}
        title={`Robot ${robotStatus.text.toLowerCase()}`}
      >
        Robot: {robotStatus.text}
      </Pill>

      {!connected && (
        <Pill tone="warn" icon={WifiOff} title="The page lost its live link to the hub">
          Reconnecting to hub…
        </Pill>
      )}

      <div className="ml-auto">
        <Btn
          variant="danger"
          size="stop"
          icon={Octagon}
          iconSize={22}
          onClick={onStop}
          title="Stop the robot immediately (no confirmation)"
        >
          STOP ROBOT
        </Btn>
      </div>
    </header>
  );
}
