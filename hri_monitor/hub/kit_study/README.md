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
  the placeholder `configs/calibration.example.yaml` (`allow_example_calibration: true`).
- `robot` — real `URBackend` against the lab UR5. **Fail-closed**: refuses to start unless
  `hub/kit_study/configs/calibration.yaml` (taught poses) exists — it never falls back to the
  example calibration on the real robot.

Full lab procedure (network, PolyScope, gripper, teaching poses, bench acceptance, sensors,
GPT judge, and Cristi's anima repo tests): see `RUNBOOK_robot.md` in this directory.

## Robot/supply/anima topics and endpoints

Bus topics: `robot.skill_queued/started/done/failed`, `robot.part_staged`, `robot.state`,
`robot.estop`; `supply.decision`, `supply.blocked`, `supply.state`; `anima.perception`,
`anima.verdict`, `anima.error`.

HTTP: `GET /api/kit/robot/state`, `POST /api/kit/robot/home`, `POST /api/kit/robot/open_gripper`,
`POST /api/kit/robot/stop`; `GET /api/kit/supply/state`, `POST /api/kit/supply/profile`
(`lookahead`, `side`, `pace`, `announce`).
