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
- STOP **latches** the robot (`robot.state.latched = "estop"`): every skill except `home` and
  `set_pace` is rejected (`robot.rejected`) and supply pauses
  (`supply.state.blocked.reason = "estop"`) until the wizard presses **Home**, which clears the
  latch (`robot.resumed`) and lets supply resume. The UI shows a red "LATCHED: … " banner on
  the robot card while this holds (plus "· supply paused"); there is no other way to clear it.
  A pace change made while latched *does* reach the robot (`set_pace` moves nothing), and is
  re-sent once on resume, so the robot never runs at the wrong speed after a stop.
- Four latch reasons, each with its own banner copy and recovery:
  - `estop` — the wizard pressed STOP → **Home**.
  - `protective_stop` — PolyScope protective stop → reset in PolyScope, then **Home**.
  - `emergency_stop` — the hardware E-stop button is pressed → "E-stop pressed — release it,
    re-power in PolyScope, then Home".
  - `robot_fault` — "robot refused/failed to move — check connection and PolyScope mode, then
    Home". Raised when the arm is not connected, a `moveJ`/`moveL` is refused, a move times out
    or the target is not reached, and by a circuit breaker after two supply failures in a row
    on *different* parts. The in-flight part is **not** marked failed; supply pauses instead of
    walking the whole order into `failed`.
- At every order transition: remove any leftover bricks from the shared mat, then press
  **Mat cleared** (`POST /api/kit/event {"type": "mat_cleared"}`) so every staged slot is
  considered free again — do this before the next order's supply starts staging into a slot
  that still (visually) looks occupied. Per-slot "Slot cleared" buttons remain for clearing one
  slot without a full mat reset.

## B. Dev laptop: URSim rehearsal (Docker)

Verified recipe (2026-09-09, this laptop). Two gotchas: `ur_rtde`'s control script makes the
robot connect *back* to the client, so plain `-p` port mapping fails with "Failed to start RTDE
data synchronization" — use `--net=host`; and with host networking the container's `Xvfb :1`
collides with the laptop's own X display `:1`, so the display is renumbered:

    docker run -d --name ursim --net=host -e ROBOT_MODEL=UR5 -e DISPLAY=:9 --entrypoint bash \
        universalrobots/ursim_e-series:5.26 \
        -c "sed -i 's/Xvfb :1/Xvfb :9/; s/-display :1/-display :9/' /entrypoint.sh && exec /entrypoint.sh"
    # (universalrobots/ursim_cb3:3.15 for a CB3 UR5; CB3 needs no Remote Control step)

Power on without the GUI, via the dashboard server (wait ~10 s for it to answer):

    printf 'power on\n' | nc -q1 127.0.0.1 29999; sleep 8
    printf 'brake release\n' | nc -q1 127.0.0.1 29999; sleep 8
    printf 'robotmode\nis in remote control\n' | nc -q1 127.0.0.1 29999   # RUNNING / false

e-Series only — Remote Control must be switched on in the GUI once per container:
`http://localhost:6080/vnc.html` (or any VNC client on `:5900`) → "Confirm Safety Configuration"
→ dismiss "Getting Started" → ☰ → Settings → System → Remote Control → **Enable** → Exit →
click the new **Local** icon in the top bar → **Remote Control**. The dashboard now answers
`is in remote control: true`; `RTDEReceive` works without this step, `RTDEControl` does not.

    URSIM_IP=127.0.0.1 .venv/bin/pytest tests/test_ursim_optional.py -q   # connect, home, gripper
    .venv/bin/python run.py --no-browser --mode ursim   # sim robot, real ur_rtde backend

`configs/mode/ursim.yaml` points at `ip: 127.0.0.1` and sets `allow_example_calibration: true`,
so it runs the real `URBackend` against URSim using the placeholder poses in
`configs/calibration.example.yaml` — no taught calibration required. The example file defines
home/transit, the three staging slots and all 14 depot slots on a placeholder grid, so a whole
block can be rehearsed; the poses are arbitrary and only meaningful inside URSim (they validate
connectivity, RTDE motion and the pick/place/gripper sequence, never table geometry). `--mode
robot` refuses this shortcut (see section C.4).

## C. Lab: UR5 (147.250.35.40, wired Ethernet from this PC)

 1. Network: set this PC's wired interface to `147.250.35.x/24 (ENSTA subnet; laptop profile `ur5-lab` = 147.250.35.134)`; `ping 147.250.35.40`. If the
    UR5 is unreachable when the app starts, `run.py` still comes up — the robot card just shows
    "disconnected" and every skill request fails until it connects. Fix the network, then press
    **Reconnect** on the robot card (`POST /api/kit/robot/connect`) rather than restarting the
    app; it re-attempts the backend connection and returns the fresh robot state.
 2. PolyScope: check version (RTDE needs ≥3.7); safety config = reduced mode + planes around
    the shared mat; e-Series → Remote Control ON. Both E-stops within reach.
 3. Gripper: **OnRobot RG2 v2, wired straight to the tool connector of the CB3** (no Compute
    Box in the lab). **Working setup (verified on site 2026-09-10):** on the pendant,
    *Installation → I/O*, set the **tool output to "controlled by user"** (not "by OnRobot"),
    tool output voltage 24 V, then **save the installation** (File → Save) so it survives a
    reboot. In that mode the gripper follows **tool digital output 0 directly: DO0 = 1 OPENS,
    DO0 = 0 CLOSES** (the output the 2024 installation had named "close"). That is what the
    app ships in `configs/mode/robot.yaml`:

            robot:
              gripper: {kind: tool_do, close_high: false}

    `close_high: false` is the polarity above; the generic default (`true`, DO0 = 1 closes)
    is what `ursim.yaml` uses. Nothing else on the robot may drive the tool outputs while the
    app runs — in particular do **not** enable "Tool Output controlled by OnRobot": the OnRobot
    URCap daemon then takes over DO0/DO1 as its own communication lines and the app's commands
    are ignored (and, as of 2026-09-10, that daemon never detected the gripper anyway —
    "Tool connector – Empty" — even after a URCap reinstall and a full reboot).

    Two alternative actuators exist in `hub/kit_study/robotd/gripper.py`, selectable with
    `robot.gripper.kind`, for the day the OnRobot software path works: **`onrobot_urcap`**
    runs the URCap-generated `rg_grip(width, force)` program on the controller (archived
    template `robotd/onrobot/rg_grip_urcap_5.15.0.script`; gives width control and grip
    detection; needs *Installation → OnRobot Setup* to show the RG2) and **`onrobot_modbus`**
    for a Compute Box (Modbus TCP :502, unit 65). Both are tested with fakes only.

    **Bench check**: `.venv/bin/python tools/gripper_test.py cycle --close-low` (open → close →
    open through tool DO0 with the lab polarity; `open|close|state` likewise); add `--modbus IP` (e.g. `--modbus 192.168.1.1`) to drive the Compute Box
    directly, or `--urcap [IP]` (defaults to the lab robot IP) to drive `rg_grip(...)` through
    the URCap exactly as the app does — `cycle --urcap` prints every RobotMessage it captured,
    which is the fastest way to confirm the URCap reinstall took (no more "Missing URCap") and
    that `rg_grip` completes cleanly. With the robot idle, confirm it opens, then confirm it
    closes on a brick without crushing it (adjust the OnRobot force/width preset — in its own UI
    for `tool_do`, or via `force_n`/`close_width_mm` in the mode file for `onrobot_modbus` /
    `onrobot_urcap`).

    **Network note**: the CB3 controller has a single Ethernet port, already used for this PC's
    wired link (step 1). The Compute Box needs its own path to both the controller and (for
    `onrobot_modbus`) this laptop — put a small switch between the PC, the CB3 controller, and
    the Compute Box rather than daisy-chaining through a port that doesn't exist. `onrobot_urcap`
    doesn't need this — it only talks to the controller, over the same link as RTDE.
 4. Teach poses (first time / after any table change). `--mode robot` is **fail-closed**: it
    refuses to start unless `hub/kit_study/configs/calibration.yaml` exists
    (`hub/kit_study/runtime.py:build_backend` raises `RobotError` otherwise) — it will never
    silently fall back to the example calibration on the real robot.

        .venv/bin/python -m hub.kit_study.robotd.teach_poses --ip 147.250.35.40 \
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

    **Robot-fault drill** (same session, 30 s): take the UR5 out of Remote Control in
    PolyScope (or unplug the Ethernet cable) while supply is staging.
      - App shows `robot.state.latched = "robot_fault"` and
        `supply.state.blocked.reason = "robot_fault"` after a *single* `robot.skill_failed` —
        no part is marked failed and no further skill is submitted.
      - Restore Remote Control / the cable, press **Reconnect** if the card still shows
        disconnected, then **Home**; supply resumes with the same part.
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

## F. Post-block questionnaires (NASA-TLX + trust)

Every block ends with the two self-reports **on the participant screen** (`/?view=screen`,
touchscreen/tablet or mouse): NASA-TLX raw (6 items, 0–100, performance runs Perfect → Failure)
then the HRTS-style trust scale (4 items, 1–7). They open automatically when the wizard presses
**Stop block**; the next **Start block** is refused (409) until both are answered or the wizard
presses **Skip questionnaires** (the skip is recorded as a row with `answers = {"skipped": …}`
and no score, so the gap is documented). Answers live in the `questionnaire` table of
`data/hri.db`, linked to the session, the recording and the condition.

    GET  /api/kit/questionnaire                    # pending / done / none (+ items and scales)
    POST /api/kit/questionnaire {instrument, answers}
    POST /api/kit/questionnaire/skip {reason}
    GET  /api/kit/questionnaires                   # every stored row (json)
    GET  /api/kit/questionnaires/nasa_tlx.csv      # participant_id,condition,mental_demand,…,overall_score
    GET  /api/kit/questionnaires/trust_hrts.csv    # participant_id,condition,reliability,…,overall_trust

The CSV layout is the one used in the Physio-HRC dataset (`questionnaires/nasa_tlx.csv`,
`questionnaires/trust_hrts.csv`), so the existing analysis scripts apply unchanged.
