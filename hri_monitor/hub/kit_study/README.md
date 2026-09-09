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

`robot.state.latched` is `"estop" | "protective_stop" | "emergency_stop" | null` — while set,
every skill except `home` is rejected (`robot.rejected {skill, args, reason}`) and a
successful `home` clears it (`robot.resumed`). `supply.state.blocked.reason` is one of
`mat_full | part_failed | estop | protective_stop | emergency_stop`. Per-skill durations are
recorded as `robot.<skill>_duration_s` (e.g. `robot.supply_duration_s`) in the CSV.

HTTP: `GET /api/kit/robot/state`, `POST /api/kit/robot/home`, `POST /api/kit/robot/open_gripper`,
`POST /api/kit/robot/stop`, `POST /api/kit/robot/connect` (re-attempts the backend connection,
returns robot state); `GET /api/kit/supply/state`, `POST /api/kit/supply/profile`
(`lookahead`, `side`, `pace`, `announce`); `POST /api/kit/event` also accepts
`{"type": "mat_cleared"}` (all staged slots considered free — use at order transitions) in
addition to the existing per-slot `{"type": "slot_cleared", "payload": {"slot": ...}}`.
`session/start` returns 409 while the robot is still busy from the previous session;
`session/stop` waits up to 6 s for any in-flight skill.
