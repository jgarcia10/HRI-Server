/** Robot health and the three recovery buttons, plus the banner for a latched stop. */
import { Bot, Hand, House, OctagonAlert, Plug } from "lucide-react";
import type { RobotState, SupplyState } from "../../lib/kit";
import { Banner, Btn, Card, Readout } from "./ui";
import { backendWord, latchAction, latchTitle, paceWord, safetyWord } from "./vocab";

export function RobotCard({
  robot,
  supply,
  error,
  onHome,
  onOpenGripper,
  onReconnect,
}: {
  robot: RobotState | null;
  supply: SupplyState | null;
  error: string | null;
  onHome: () => void;
  onOpenGripper: () => void;
  onReconnect: () => void;
}) {
  const connected = !!robot?.connected;
  const latched = robot?.latched ?? null;
  return (
    <Card icon={Bot} title="Robot" hint="Safety and recovery." error={error}>
      {latched && (
        <Banner tone="err" icon={OctagonAlert} title={latchTitle(latched)}>
          {latchAction(latched)}
          {supply?.paused && " Deliveries are paused until then."}
        </Banner>
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Readout
          label="Connection"
          value={connected ? backendWord(robot?.backend) : "Disconnected"}
          tone={connected ? "muted" : "err"}
        />
        <Readout
          label="Safety"
          value={latched ? "Stopped" : safetyWord(robot?.safety)}
          tone={latched || (robot && robot.safety !== "normal") ? "err" : "ok"}
        />
        <Readout label="Gripper" value={robot?.gripper_closed ? "Closed" : "Open"} />
        <Readout
          label="Doing"
          value={robot?.busy ? "Moving" : robot?.queue ? `${robot.queue} queued` : "Idle"}
        />
      </div>
      <p className="-mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
        Speed {paceWord(robot?.pace).toLowerCase()}
        {robot?.last_skill ? ` · last move: ${robot.last_skill.replace(/_/g, " ")}` : ""}
      </p>

      <div className="flex flex-wrap gap-2">
        <Btn
          variant={latched ? "primary" : "neutral"}
          icon={House}
          onClick={onHome}
          title="Send the arm back to its home pose — also clears a stop"
        >
          Home
        </Btn>
        <Btn
          variant="neutral"
          icon={Hand}
          onClick={onOpenGripper}
          title="Open the gripper (releases a brick it is holding)"
        >
          Open gripper
        </Btn>
        <Btn
          variant={connected ? "quiet" : "warn"}
          icon={Plug}
          onClick={onReconnect}
          title={
            connected
              ? "Re-open the connection to the arm"
              : "The arm is not connected — try to connect again"
          }
        >
          Reconnect
        </Btn>
      </div>
    </Card>
  );
}
