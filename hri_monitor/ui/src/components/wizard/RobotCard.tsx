/** Robot health and the three recovery buttons, plus the banner for a latched stop. */
import { Bot, Grip, Hand, House, OctagonAlert, Plug, RotateCcw } from "lucide-react";
import type { RobotState, SupplyState } from "../../lib/kit";
import { Banner, Btn, Card, Readout } from "./ui";
import { backendWord, latchAction, latchTitle, paceWord, safetyWord } from "./vocab";

export function RobotCard({
  robot,
  supply,
  error,
  onHome,
  onOpenGripper,
  onCloseGripper,
  onResetGripper,
  onReconnect,
}: {
  robot: RobotState | null;
  supply: SupplyState | null;
  error: string | null;
  onHome: () => void;
  onOpenGripper: () => void;
  onCloseGripper: () => void;
  onResetGripper: () => void;
  onReconnect: () => void;
}) {
  const connected = !!robot?.connected;
  const latched = robot?.latched ?? null;
  const busy = !!robot?.busy;
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

      <div className="flex flex-col gap-1.5">
        <p className="text-[11px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
          Gripper
        </p>
        <div className="flex flex-wrap gap-2">
          <Btn
            variant="neutral"
            icon={Grip}
            onClick={onCloseGripper}
            disabled={busy}
            title={busy ? "Wait for the current robot action to finish" : "Close the gripper"}
          >
            Close gripper
          </Btn>
          <Btn
            variant="neutral"
            icon={Hand}
            onClick={onOpenGripper}
            disabled={busy}
            title={
              busy
                ? "Wait for the current robot action to finish"
                : "Open the gripper (releases a brick it is holding)"
            }
          >
            Open gripper
          </Btn>
          <Btn
            variant="neutral"
            icon={RotateCcw}
            onClick={onResetGripper}
            disabled={busy}
            title={
              busy
                ? "Wait for the current robot action to finish"
                : "Recover the gripper after it stopped responding"
            }
          >
            Reset gripper
          </Btn>
        </div>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Reset gripper takes ~35 s — use it if the gripper stops responding after closing on
          empty air.
        </p>
      </div>
    </Card>
  );
}
