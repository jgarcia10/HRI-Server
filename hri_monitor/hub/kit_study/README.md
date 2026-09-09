# hub/kit_study — Anticipate, Regulate, Remember (kit-assembly study)

M1 layer: task engine + participant screen + wizard, recording through the standard
hri_monitor pipeline. Spec: `ICRA 2027 - Cristi/docs/superpowers/specs/2026-09-03-kit-study-integration-design.md`.

## Run a sim block (no hardware)

    cd hri_monitor
    .venv/bin/python run.py --no-browser      # sensors per config.yaml (simulate: true ok)

- Participant display → http://127.0.0.1:8000/?view=screen (fullscreen, F11)
- Experimenter      → http://127.0.0.1:8000/ → "Kit Study" page: set participant code,
  condition C0/C1, Start block. Mark parts with "Part placed"; advance with "Next order";
  annotate repositions and speech with the buttons.
- Data → Experiments page ("Kit Study" experiment): recording CSV has `task.*` +
  `wizard.*` + sensor rows on one clock; markers at order/perturbation boundaries.

Block config: `hub/kit_study/configs/orders_f1.yaml` (family F1; `orders_f2.yaml` also present).

## Modes

`run.py --mode sim|ursim|robot` (default `sim`) picks the robot backend via
`hub/kit_study/configs/mode/{sim,ursim,robot}.yaml`; `--robot-ip` overrides the IP in the
chosen mode file.

- `sim` — scripted `SimBackend`, no hardware, no calibration file needed.
- `ursim` — real `URBackend` over `ur_rtde` against a Docker URSim at `127.0.0.1`; runs with
  the placeholder `configs/calibration.example.yaml` (`allow_example_calibration: true`; all 14 depot
  slots on an arbitrary grid — validates motion/RTDE, not table geometry).
- `robot` — real `URBackend` against the lab UR5. **Fail-closed**: refuses to start unless
  `hub/kit_study/configs/calibration.yaml` (taught poses) exists — it never falls back to the
  example calibration on the real robot. If the UR5 is unreachable, the app still starts (the
  robot card shows disconnected); fix the network and press **Reconnect**.

Full lab procedure (network, PolyScope, gripper, teaching poses, bench acceptance, sensors,
GPT judge, and Cristi's anima repo tests): see `RUNBOOK_robot.md` in this directory.

## Robot/supply/anima topics and endpoints

Bus topics: `robot.skill_queued/started/done/failed`, `robot.part_staged`, `robot.state`,
`robot.estop`, `robot.rejected`, `robot.resumed`; `supply.decision`, `supply.blocked`,
`supply.state`; `anima.perception`, `anima.verdict`, `anima.error`.

`robot.state.latched` is `"estop" | "protective_stop" | "emergency_stop" | "robot_fault" |
null` — while set, every skill except `home` and `set_pace` is rejected
(`robot.rejected {skill, args, reason}`) and a successful `home` clears it (`robot.resumed`).
`set_pace` is admitted because it commands no motion: without that, a pace change made during
a stop would never reach the robot and it would run at `normal` while the profile and the CSV
say `slow`. `supply.state.blocked.reason` is one of
`mat_full | part_failed | estop | protective_stop | emergency_stop | robot_fault`, and
`supply.state.paused` says whether supply is holding.

The four robot-side reasons and what the wizard has to do:

| reason | meaning | recovery |
| --- | --- | --- |
| `estop` | the wizard pressed STOP | press **Home** |
| `protective_stop` | PolyScope protective stop | reset in PolyScope, then **Home** |
| `emergency_stop` | the hardware E-stop button is pressed | release it, re-power in PolyScope, then **Home** |
| `robot_fault` | the robot refused/failed to move — not connected, `moveJ/moveL refused`, `move timeout`, `target not reached`, or two supply failures in a row on different parts | check the connection and PolyScope mode, then **Home** |

`robot.skill_failed` carries `{protective_stop, aborted, robot_fault, safety}`; `safety` is
the latch reason when the failure latched the bridge and `null` for an ordinary grasp miss
(which supply retries once). Per-skill durations are recorded as `robot.<skill>_duration_s`
(e.g. `robot.supply_duration_s`) in the CSV.

HTTP: `GET /api/kit/robot/state`, `POST /api/kit/robot/home`, `POST /api/kit/robot/open_gripper`,
`POST /api/kit/robot/stop`, `POST /api/kit/robot/connect` (re-attempts the backend connection,
returns robot state); `GET /api/kit/supply/state`, `POST /api/kit/supply/profile`
(`lookahead`, `side`, `pace`, `announce`); `POST /api/kit/event` also accepts
`{"type": "mat_cleared"}` (all staged slots considered free — use at order transitions) in
addition to the existing per-slot `{"type": "slot_cleared", "payload": {"slot": ...}}`.
`session/start` returns 409 while the robot is still busy from the previous session;
`session/stop` waits up to 25 s for any in-flight skill (a URSim supply cycle measured 22 s;
lab cycles are ≤ 5 s). Process shutdown stops the session first, then the bridge, then the
LLM worker, so a Ctrl-C mid-block still closes the recording.

## Questionnaires

After each block the participant answers NASA-TLX and a trust scale on their screen
(`hub/kit_study/questionnaires.py`; stored in the `questionnaire` table; exported by
`/api/kit/questionnaires/{nasa_tlx|trust_hrts}.csv` in the Physio-HRC layout). A new block cannot
start while they are pending — see RUNBOOK §F.
