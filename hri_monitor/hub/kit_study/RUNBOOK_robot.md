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
  e-stops the backend) and remains **one click, no confirmation dialog**.
- STOP **latches** the robot (`robot.state.latched = "estop"`): every skill except `home` is
  rejected (`robot.rejected`) and supply pauses (`supply.state.blocked.reason = "estop"`) until
  the wizard presses **Home**, which clears the latch (`robot.resumed`) and lets supply resume.
  The UI shows a red "LATCHED: estop — press Home to resume" banner on the robot card while
  this holds; there is no other way to clear it.
- At every order transition: remove any leftover bricks from the shared mat, then press
  **Mat cleared** (`POST /api/kit/event {"type": "mat_cleared"}`) so every staged slot is
  considered free again — do this before the next order's supply starts staging into a slot
  that still (visually) looks occupied. Per-slot "Slot cleared" buttons remain for clearing one
  slot without a full mat reset.

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

 1. Network: set this PC's wired interface to `192.168.131.x/24`; `ping 192.168.131.140`. If the
    UR5 is unreachable when the app starts, `run.py` still comes up — the robot card just shows
    "disconnected" and every skill request fails until it connects. Fix the network, then press
    **Reconnect** on the robot card (`POST /api/kit/robot/connect`) rather than restarting the
    app; it re-attempts the backend connection and returns the fresh robot state.
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
    (`robot.<skill>_duration_s`, e.g. `robot.supply_duration_s`, in the CSV).

    **Protective-stop drill** (do this once per bench session): with the robot mid-skill (or
    idle — a ~3 Hz monitor also catches it while idle), push on the arm hard enough to trigger
    PolyScope's protective stop.
      - App shows `robot.state.latched = "protective_stop"`; the in-flight part is **not**
        marked failed, supply pauses (`supply.state.blocked.reason = "protective_stop"`), and
        the UI blocked-banner reads "Robot stopped — reset in PolyScope if needed, then Home".
      - In PolyScope: clear the protective stop / release the safeguard, back to Normal.
      - In the wizard: press **Home**. This clears the latch (`robot.resumed`) and supply
        resumes automatically with the *same* part it was staging — no re-queue needed.
      - Confirm no `part_failed` was recorded for that part and the CSV has a `blocked` marker
        around the drill.
 6. Sensors: Shimmer → Devices page (bind rfcomm, connect); Optris → status connected
    (`Formats.def` now present in `/usr/share/libirimager`); webcam index in `config.yaml`.

## D. LLM (perception/judge)

`hub/kit_study/configs/llm.yaml` keys, as they exist in the file today:

    provider: mock          # mock | openai   (set openai + export OPENAI_API_KEY for real runs)
    model: gpt-5-mini
    mission: "..."           # fixed ANIMA mission text for perceive()/judge()
    judge_every: 2           # judge() runs once every N human (wizard.speech) turns
    history: 6               # turns of context passed to perceive()/judge()
    cache_dir: null          # disk cache dir; null disables the cache — REQUIRED for live runs
    timeout_s: 20            # OpenAI client timeout, seconds
    max_retries: 1           # OpenAI client retry count
    reasoning_budget: 2048   # extra max_output_tokens reserved for gpt-5 reasoning tokens

`provider: mock` is the checked-in default, so rehearsals (sections A and B, and CI) never
call an LLM and cost nothing. For a real run: `export OPENAI_API_KEY=sk-...`, set
`provider: openai` in `llm.yaml`. `judge_every` is the cost guard — perception runs on every
wizard-speech turn, but the (usually pricier) judge call only every `judge_every` turns.

**`cache_dir` must stay `null` for every live participant session.** The on-disk LLM cache
keys purely on (system, prompt, schema, max_tokens, effort, salt) — it does not know about
participants — so a non-null `cache_dir` shared across a study would silently serve a cached
perception/verdict for identical prompts (e.g. repeated "wait"), producing zero-latency,
zero-usage responses that are not a real measurement. Only set it (e.g. `.llm_cache`) for
offline, single-operator rehearsals where deterministic replay is wanted.

`timeout_s`/`max_retries` bound the OpenAI client (its own defaults are 600s and 2 retries —
both too permissive for a live wizard turn). `reasoning_budget` is added on top of the
caller's `max_tokens` (384 for the judge, 512 for perception) whenever reasoning is enabled:
on gpt-5 models, reasoning tokens are billed against `max_output_tokens`, so without this
headroom the model spends the whole budget on hidden reasoning, returns
`status="incomplete"`, and the call raises instead of returning an answer — the entire
`anima.*` stream would otherwise silently stop while `provider: openai` is on. These three
keys only take effect when `provider: openai`.

## E. Cristi's anima repo tests

Repo: `/home/juanjose-ensta/Documents/ENSTA/ICRA 2027 - Cristi/anima`, branch `openai-backend`.

    cd "/home/juanjose-ensta/Documents/ENSTA/ICRA 2027 - Cristi/anima"
    env -u PYTHONPATH /home/juanjose-ensta/Documents/HRIServcer/hri_monitor/.venv/bin/pytest -q

The anima repo has no `.venv` of its own — it borrows `hri_monitor`'s venv (same interpreter,
`anima` is importable from there). `env -u PYTHONPATH` matters here: the ambient ROS
`PYTHONPATH` on this machine breaks pytest's plugin discovery, so it must be unset for the
anima test suite specifically (not needed for `hri_monitor`'s own `.venv/bin/pytest` runs from
`hri_monitor/`, which don't inherit that path). `OpenAIBackend` (`anima/llm/backend.py`) talks
to GPT via the Responses API (`client.responses.create(...)`), reads `OPENAI_API_KEY` from the
environment (same key as section D), and applies `timeout_s`/`max_retries`/`reasoning_budget`
from `llm.yaml` — see section D for why those matter.
