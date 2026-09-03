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

Block config: `hub/kit_study/configs/orders_f1.yaml` (family F1; F2 arrives with M2+).
