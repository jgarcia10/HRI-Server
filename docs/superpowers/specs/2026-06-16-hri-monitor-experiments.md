# HRI Monitor — Experiments Page (Data Collection)

**Date:** 2026-06-16
**Status:** Approved pending user review
**Scope:** A new Experiments page + backend to define studies, run sessions, record physiological signals per condition with event markers, and browse/export the data. Builds on the existing bus / sensor / manager architecture and the Clinical Frost UI. **Statistical analysis is a separate, later milestone** (Analysis page).

## 1. Goal

Let a researcher run HRI experiments and collect physiological data:
1. Define an **experiment** (name, description, ordered **conditions**, predefined **marker labels**) and its **participant** roster.
2. Run a **session** for a participant: select a condition, **Start/Stop** recording, watch live signals, drop timestamped **markers**.
3. Record the numeric physiological signals to disk (tidy CSV + SQLite metadata).
4. **Browse** past sessions/recordings and **export** tidy CSV (per recording) or a session `.zip` bundle.

Records whatever numeric topics are on the bus now (`shimmer.gsr`, `shimmer.ppg`, `ppg.hr`, `ppg.hrv`, `rgb.blink`, `thermal.temps`); `model.estimates` is added automatically once milestone 3 publishes it. Video frames are **not** recorded.

## 2. Decisions (from brainstorming)

- **Scope:** data collection + management only. Statistics = next milestone.
- **What is recorded:** numeric signals + markers only (no video).
- **CSV layout:** tidy **long** — `t_offset, signal, value` (one row per sample).
- **Run workflow:** a dedicated **Run console** inside the Experiments page (tabs: Manage / Run / Browse).
- **Markers:** predefined per-experiment quick-buttons **plus** free text.
- **Storage:** **SQLite** metadata (`data/hri.db`) + **one tidy CSV per recording** (`data/recordings/<id>.csv`).
- **Participants are per-experiment** (each experiment owns its roster; code unique within the experiment).

## 3. Data model (SQLite, `data/hri.db`)

```
experiment(id, name, description, created_at)
condition(id, experiment_id, name, order_index)                    -- ordered named conditions
marker_label(id, experiment_id, label)                             -- predefined quick-button labels
participant(id, experiment_id, code, notes, created_at)            -- per-experiment; (experiment_id, code) unique
session(id, experiment_id, participant_id, started_at, notes)
recording(id, session_id, condition_id, started_at, stopped_at,
          csv_path, sample_count, status)                          -- status: active|completed|interrupted
marker(id, recording_id, t_offset, label, source)                  -- t_offset secs from recording start; source: button|text
```

Foreign keys ON; deleting an experiment cascades conditions/labels/participants/sessions/recordings/markers and removes the recordings' CSV files. Deleting a participant cascades their sessions/recordings/markers + CSVs. SQLite opened with `PRAGMA foreign_keys=ON`; a tiny `schema_version` enables future migrations.

## 4. Recorder (`hub/experiments/recorder.py`)

A **bus subscriber** capturing full-rate data (not the decimated dashboard stream).

- `Recorder(bus, csv_path)`: `start()` subscribes to the recorded topics; `add_sample` callback appends rows to an in-memory buffer; a background flusher writes buffered rows to the CSV ~once per second (and on stop).
- Recorded topics: `shimmer.gsr`, `shimmer.ppg`, `ppg.hr`, `ppg.hrv`, `rgb.blink`, `model.estimates` → one row each (`value` from the payload's numeric field); `thermal.temps` → expands to four rows `thermal.forehead/left_cheek/right_cheek/nose`.
- `t_offset` = `message.ts − start_ts` (seconds, float).
- CSV header: `t_offset,signal,value`. Append mode; created with header on start.
- `stop()` flushes, unsubscribes, returns `sample_count`.
- A signal whose sensor is down simply stops producing rows — recording continues regardless.

**Topic → value mapping** (pure, unit-tested): `shimmer.gsr/ppg`→`value`; `ppg.hr/hrv`→`value`; `rgb.blink`→`rate`; `thermal.temps`→4 ROI floats; `model.estimates`→`cognitive_load` and `trust` as two rows.

## 5. Recording controller (`hub/experiments/controller.py`)

Single source of truth for the one active recording.

- `start(session_id|new_session_args, condition_id)`: refuse if one is active; create the `recording` row (status active); spin up a `Recorder`; record start time.
- `marker(label, source)`: insert a `marker` with current `t_offset`.
- `stop()`: stop the recorder, finalize the `recording` (stopped_at, sample_count, status=completed); idempotent.
- `status()`: `{recording_id, condition, elapsed, sample_count, markers}` or `None`.
- On hub startup, any `recording` left `active` is reconciled to `interrupted` (keeps the partial CSV).
- Thread-safe (recorder runs on bus/publisher threads; controller methods called from request threads under a lock).

## 6. REST API (`hub/experiments/router.py`, mounted in `server.py`)

Management:
- `GET/POST /api/experiments`; `GET/PATCH/DELETE /api/experiments/{id}` (returns conditions + marker_labels nested)
- `PUT /api/experiments/{id}/conditions` (replace ordered list); `PUT /api/experiments/{id}/marker-labels`
- `GET/POST /api/experiments/{id}/participants`; `PATCH/DELETE /api/participants/{id}`

Run:
- `POST /api/recordings/start` — `{experiment_id, participant_id, condition_id, session_id?}` (creates a session if `session_id` omitted) → `{recording_id}`
- `POST /api/recordings/{id}/marker` — `{label, source}`
- `POST /api/recordings/{id}/stop`
- `GET /api/recordings/active` → controller status (also pushed on `/ws` as `recording.status` for smooth timer/counter updates)

Browse & export:
- `GET /api/experiments/{id}/sessions` (sessions → recordings → marker counts)
- `GET /api/recordings/{id}` (metadata + markers)
- `GET /api/recordings/{id}/export.csv` → the tidy CSV
- `GET /api/sessions/{id}/export.zip` → every recording CSV + `session.json` (experiment, participant, conditions, markers) + `manifest.csv` (recording→condition map)

All new routes registered before the static UI mount. Existing endpoints unchanged.

## 7. UI (`ui/src/pages/Experiments.tsx`, Clinical Frost)

Replaces the sidebar "Experiments" placeholder; three tabs.

- **Manage:** experiment list + editor (name, description, ordered conditions, marker labels); per-experiment participant roster (code, notes).
- **Run:** experiment + participant selectors (+ "new participant" inline), condition chips, **Start/Stop**, a red pinned recording bar (elapsed timer + live sample count + sensor status), four live `SignalChart`s, and a marker panel (predefined quick-buttons + free-text input) with a live marker list. Status/timer/counter driven by `GET /api/recordings/active` + the `recording.status` WS message.
- **Browse:** sessions grouped by participant; each recording row shows started/duration/samples/markers with **CSV** download; per-session **.zip** export button.

Support: `ui/src/lib/experiments.ts` (typed API client + `useExperiments()` / `useActiveRecording()` hooks), small components (`ExperimentEditor`, `ParticipantList`, `RunConsole`, `RecordBar`, `MarkerPanel`, `SessionBrowser`). Reuses `SignalChart`, `StatusChip`, tokens. Rebuilt `ui_dist` committed.

## 8. Error handling

- One active recording enforced; second `start` → clear 409-style error; `stop` idempotent.
- Incremental ~1 s flush → crash leaves a valid CSV; `active`→`interrupted` reconciliation on startup.
- Sensor drop mid-recording is non-fatal (that signal pauses; recording continues).
- Deletes confirm + cascade (DB + CSV files); no silent orphans.
- CSV write errors logged + surfaced on recording status, never crash the hub.

## 9. Testing (hardware-free, pytest)

- `db.py`: schema, CRUD, cascade deletes, unique (experiment_id, code), migrations.
- `recorder.py`: synthetic bus messages → exact tidy rows (incl. `thermal.temps`→4 rows), flush, finalize; the topic→value mapping as pure unit tests.
- `controller.py`: only-one-active guard, start/marker/stop lifecycle, t_offset correctness, interrupted recovery.
- API: FastAPI test client + temp DB — create experiment/participant, start→marker→stop, browse, CSV/zip export contents.
- Existing 58 tests stay green. No hardware: the recorder uses the in-process `MessageBus`.

## 10. Out of scope

- Statistical analysis / condition comparison (next milestone — Analysis page).
- Video (thermal/RGB frame) recording.
- CL/T model estimates (milestone 3) — recorded automatically once the topic exists; not built here.
- ROS event recording (milestone 4); multi-user/auth; cloud sync; trial/protocol auto-advance engine (conditions are recorded manually).
