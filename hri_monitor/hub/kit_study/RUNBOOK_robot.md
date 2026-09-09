# RUNBOOK — robot-in-the-loop (UR5 via ur_rtde)

All commands run from `hri_monitor/` unless noted. `run.py` takes `--mode sim|robot|ursim`
(default `sim`) and an optional `--robot-ip` that overrides the IP baked into the mode file
(`hub/kit_study/runtime.py:load_mode`). Mode files live in `hub/kit_study/configs/mode/`.

## A. Dev laptop: sim rehearsal (no hardware)

    cd hri_monitor && .venv/bin/python run.py --no-browser --mode sim

- `configs/mode/sim.yaml`: `robot.backend: sim` (scripted timings, no I/O), `supply.lookahead: 1`.
- Participant display → `http://127.0.0.1:8000/?view=screen` (fullscreen, F11).
- Experimenter → `http://127.0.0.1:8000/` → "Kit Study" page (wizard): set participant code +
  condition, Start block → parts appear on the staging slots (per the look-ahead) → click
  "Part placed" as the participant would → change look-ahead/side/pace live from the wizard →
  "STOP robot" is available at any time (`POST /api/kit/robot/stop`, clears the queue and
  e-stops the backend).

## B. Dev laptop: URSim rehearsal (Docker)

    docker run --rm -it -p 5900:5900 -p 6080:6080 -p 29999:29999 -p 30001-30004:30001-30004 \
        universalrobots/ursim_e-series:5.26          # (use universalrobots/ursim_cb3:3.15 for a CB3 UR5)

Open `http://localhost:6080/vnc.html` → power on → brake release → Settings → System →
Remote Control: enable, then switch to Remote (e-Series). CB3: just have no local program
running.

    URSIM_IP=127.0.0.1 .venv/bin/pytest tests/test_ursim_optional.py -q
    .venv/bin/python run.py --no-browser --mode ursim   # sim robot, real ur_rtde backend

`configs/mode/ursim.yaml` points at `ip: 127.0.0.1` and sets `allow_example_calibration: true`,
so it runs the real `URBackend` against URSim using the placeholder poses in
`configs/calibration.example.yaml` — no taught calibration required. The example file defines
home/transit, the three staging slots and all 14 depot slots on a placeholder grid, so a whole
block can be rehearsed; the poses are arbitrary and only meaningful inside URSim (they validate
connectivity, RTDE motion and the pick/place/gripper sequence, never table geometry). `--mode
robot` refuses this shortcut (see section C.4).

## C. Lab: UR5 (192.168.131.140, wired Ethernet from this PC)

 1. Network: set this PC's wired interface to `192.168.131.x/24`; `ping 192.168.131.140`.
 2. PolyScope: check version (RTDE needs ≥3.7); safety config = reduced mode + planes around
    the shared mat; e-Series → Remote Control ON. Both E-stops within reach.
 3. Gripper (OnRobot on tool digital output 0): with the robot idle, `open_gripper` from the
    wizard, confirm it opens; confirm it closes on a brick without crushing it (adjust the
    OnRobot force/width preset in its own UI if needed).
 4. Teach poses (first time / after any table change). `--mode robot` is **fail-closed**: it
    refuses to start unless `hub/kit_study/configs/calibration.yaml` exists
    (`hub/kit_study/runtime.py:build_backend` raises `RobotError` otherwise) — it will never
    silently fall back to the example calibration on the real robot.

        .venv/bin/python -m hub.kit_study.robotd.teach_poses --ip 192.168.131.140 \
          --out hub/kit_study/configs/calibration.yaml \
          --slots home transit L C R \
            RD1 RD2 RD3 OR1 OR2 OR3 BL1 BL2 SF1 SF2 SF3 LM1 LM2 LM3

    (`home transit L C R` plus every depot slot named across `orders_f1.yaml` and
    `orders_f2.yaml`, verified with `grep -h depot_slot hub/kit_study/configs/orders_f*.yaml`: RD1-3, OR1-3,
    BL1-2, SF1-3, LM1-3.) Grasp pose = jaws around the brick below the stud, gripper open.
 5. Bench (spec M4 exit): `run.py --mode robot`; from the wizard: Home, then start a block with
    a team member placing parts; log ≥ 40 supply cycles; require ≥95% success, cycle ≤ 5 s p95
    (`robot.skill_duration_s` in the CSV), one protective-stop drill (push the arm → app shows
    `protective_stop`, STOP robot, reset in PolyScope, Home resumes).
 6. Sensors: Shimmer → Devices page (bind rfcomm, connect); Optris → status connected
    (`Formats.def` now present in `/usr/share/libirimager`); webcam index in `config.yaml`.

## D. LLM (perception/judge)

`hub/kit_study/configs/llm.yaml` keys, as they exist in the file today:

    provider: mock          # mock | openai   (set openai + export OPENAI_API_KEY for real runs)
    model: gpt-5-mini
    mission: "..."           # fixed ANIMA mission text for perceive()/judge()
    judge_every: 2           # judge() runs once every N human (wizard.speech) turns
    history: 6               # turns of context passed to perceive()/judge()

`provider: mock` is the checked-in default, so rehearsals (sections A and B, and CI) never
call an LLM and cost nothing. For a real run: `export OPENAI_API_KEY=sk-...`, set
`provider: openai` in `llm.yaml`. `judge_every` is the cost guard — perception runs on every
wizard-speech turn, but the (usually pricier) judge call only every `judge_every` turns.

## E. Cristi's anima repo tests

Repo: `/home/juanjose-ensta/Documents/ENSTA/ICRA 2027 - Cristi/anima`, branch `openai-backend`.

    cd "/home/juanjose-ensta/Documents/ENSTA/ICRA 2027 - Cristi/anima"
    env -u PYTHONPATH .venv/bin/pytest -q

`env -u PYTHONPATH` matters here: the ambient ROS `PYTHONPATH` on this machine breaks pytest's
plugin discovery, so it must be unset for the anima test suite specifically (not needed for
`hri_monitor`'s own `.venv/bin/pytest`, which doesn't inherit that path). `OpenAIBackend`
(`anima/llm/backend.py`) talks to GPT via the Responses API (`client.responses.create(...)`)
and reads `OPENAI_API_KEY` from the environment — same key as section D.
