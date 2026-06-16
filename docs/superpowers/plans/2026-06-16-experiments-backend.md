# Experiments Backend — Data Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SQLite-backed experiment/participant/session/recording/marker model, a bus-subscriber recorder that writes tidy-long CSV at full sensor rate, a single-active-recording controller, and the REST API to manage studies, run recordings, and browse/export — all hardware-free testable.

**Architecture:** A new `hub/experiments/` package: `db.py` (schema + queries over stdlib `sqlite3`), `recorder.py` (subscribes to the in-process `MessageBus`, buffers samples, flushes tidy CSV ~1 Hz), `controller.py` (enforces one active recording, owns lifecycle, reconciles interrupted recordings at startup), and `router.py` (FastAPI routes mounted into the existing app). No new Python dependencies. Sensors/manager are untouched — the recorder just listens to the same bus.

**Tech Stack:** Python 3.10, stdlib `sqlite3` + `csv` + `zipfile`, FastAPI, pytest. No pandas/parquet.

**Spec:** `docs/superpowers/specs/2026-06-16-hri-monitor-experiments.md` (read §3–§9).

**Working dir:** `/home/juanjose-ensta/Documents/HRIServcer/hri_monitor`. Tests: `.venv/bin/python -m pytest`. `pytest.ini` sets pythonpath=. and disables ROS plugins — don't touch it. Baseline: 58 tests pass.

**Tidy CSV contract:** header `t_offset,signal,value`; one row per sample; `thermal.temps` expands to rows `thermal.forehead/left_cheek/right_cheek/nose`.

---

### Task 1: Topic → sample rows (pure mapping)

**Files:**
- Create: `hri_monitor/hub/experiments/__init__.py` (empty)
- Create: `hri_monitor/hub/experiments/signals.py`
- Test: `hri_monitor/tests/test_exp_signals.py`

- [ ] **Step 1: Create the empty package marker**

```bash
mkdir -p hri_monitor/hub/experiments
touch hri_monitor/hub/experiments/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `hri_monitor/tests/test_exp_signals.py`:

```python
from hub.experiments.signals import RECORDED_TOPICS, sample_rows


def test_scalar_topics_map_to_one_row():
    assert sample_rows("shimmer.gsr", {"value": 4.21}) == [("shimmer.gsr", 4.21)]
    assert sample_rows("ppg.hr", {"value": 72.0}) == [("ppg.hr", 72.0)]
    assert sample_rows("rgb.blink", {"rate": 17.2, "ear": 0.3}) == [("rgb.blink", 17.2)]


def test_thermal_temps_expands_to_four_rows():
    rows = sample_rows("thermal.temps",
                       {"forehead": 34.5, "left_cheek": 33.8, "right_cheek": 33.9, "nose": 32.5})
    assert ("thermal.forehead", 34.5) in rows
    assert ("thermal.left_cheek", 33.8) in rows
    assert len(rows) == 4


def test_model_estimates_expands_to_two_rows():
    rows = sample_rows("model.estimates", {"cognitive_load": 0.4, "trust": 0.7})
    assert set(rows) == {("model.cognitive_load", 0.4), ("model.trust", 0.7)}


def test_unknown_topic_yields_nothing():
    assert sample_rows("device.status", {"device": "rgb", "status": "connected"}) == []


def test_recorded_topics_set():
    assert RECORDED_TOPICS == {
        "shimmer.gsr", "shimmer.ppg", "ppg.hr", "ppg.hrv",
        "rgb.blink", "thermal.temps", "model.estimates",
    }
```

- [ ] **Step 3: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_exp_signals.py -v`
Expected: FAIL — module missing.

- [ ] **Step 4: Implement**

Create `hri_monitor/hub/experiments/signals.py`:

```python
"""Map a bus message (topic, data) to tidy CSV rows (signal, value). Pure."""

RECORDED_TOPICS = {
    "shimmer.gsr", "shimmer.ppg", "ppg.hr", "ppg.hrv",
    "rgb.blink", "thermal.temps", "model.estimates",
}
_THERMAL_ROIS = ("forehead", "left_cheek", "right_cheek", "nose")


def sample_rows(topic: str, data: dict) -> list[tuple[str, float]]:
    """Return [(signal, value), ...] for one bus message; [] for un-recorded topics."""
    if topic in ("shimmer.gsr", "shimmer.ppg", "ppg.hr", "ppg.hrv"):
        return [(topic, float(data["value"]))]
    if topic == "rgb.blink":
        return [("rgb.blink", float(data["rate"]))]
    if topic == "thermal.temps":
        return [(f"thermal.{roi}", float(data[roi])) for roi in _THERMAL_ROIS if roi in data]
    if topic == "model.estimates":
        out = []
        if "cognitive_load" in data:
            out.append(("model.cognitive_load", float(data["cognitive_load"])))
        if "trust" in data:
            out.append(("model.trust", float(data["trust"])))
        return out
    return []
```

- [ ] **Step 5: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_exp_signals.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add hri_monitor/hub/experiments/__init__.py hri_monitor/hub/experiments/signals.py hri_monitor/tests/test_exp_signals.py
git commit -m "feat(experiments): topic->tidy-row signal mapping"
```

---

### Task 2: Database layer (schema + CRUD)

**Files:**
- Create: `hri_monitor/hub/experiments/db.py`
- Test: `hri_monitor/tests/test_exp_db.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_exp_db.py`:

```python
import pytest

from hub.experiments.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "hri.db")


def test_create_experiment_with_conditions_and_labels(db):
    exp = db.create_experiment("Trust Study", "desc")
    db.set_conditions(exp, ["Baseline", "Transparent", "Opaque"])
    db.set_marker_labels(exp, ["Stimulus onset", "Robot error"])
    got = db.get_experiment(exp)
    assert got["name"] == "Trust Study"
    assert [c["name"] for c in got["conditions"]] == ["Baseline", "Transparent", "Opaque"]
    assert [c["order_index"] for c in got["conditions"]] == [0, 1, 2]
    assert sorted(l["label"] for l in got["marker_labels"]) == ["Robot error", "Stimulus onset"]


def test_participant_code_unique_per_experiment(db):
    exp = db.create_experiment("S", "")
    db.create_participant(exp, "P01", "")
    with pytest.raises(Exception):
        db.create_participant(exp, "P01", "")
    # same code in a different experiment is fine
    exp2 = db.create_experiment("S2", "")
    assert db.create_participant(exp2, "P01", "") > 0


def test_session_recording_marker_flow(db):
    exp = db.create_experiment("S", "")
    db.set_conditions(exp, ["Baseline"])
    cond = db.get_experiment(exp)["conditions"][0]["id"]
    part = db.create_participant(exp, "P01", "")
    sess = db.create_session(exp, part)
    rec = db.create_recording(sess, cond, "data/recordings/1.csv")
    db.add_marker(rec, 1.5, "Robot error", "button")
    db.finalize_recording(rec, sample_count=10, status="completed")
    detail = db.get_recording(rec)
    assert detail["status"] == "completed" and detail["sample_count"] == 10
    assert detail["markers"][0]["label"] == "Robot error"
    assert detail["markers"][0]["t_offset"] == 1.5


def test_delete_experiment_cascades(db):
    exp = db.create_experiment("S", "")
    db.set_conditions(exp, ["Baseline"])
    cond = db.get_experiment(exp)["conditions"][0]["id"]
    part = db.create_participant(exp, "P01", "")
    sess = db.create_session(exp, part)
    rec = db.create_recording(sess, cond, "x.csv")
    db.delete_experiment(exp)
    assert db.get_experiment(exp) is None
    assert db.get_recording(rec) is None


def test_active_recordings_reconciled_to_interrupted(db):
    exp = db.create_experiment("S", "")
    db.set_conditions(exp, ["Baseline"])
    cond = db.get_experiment(exp)["conditions"][0]["id"]
    part = db.create_participant(exp, "P01", "")
    sess = db.create_session(exp, part)
    rec = db.create_recording(sess, cond, "x.csv")  # left 'active'
    assert db.get_recording(rec)["status"] == "active"
    n = db.reconcile_active_recordings()
    assert n == 1
    assert db.get_recording(rec)["status"] == "interrupted"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_exp_db.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `hri_monitor/hub/experiments/db.py`:

```python
"""SQLite metadata store for experiments/participants/sessions/recordings/markers.
Stdlib sqlite3 only. One Database instance per process; methods are short-lived
connections so they are safe to call from multiple threads."""
import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS experiment (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT DEFAULT '',
  created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS condition (
  id INTEGER PRIMARY KEY, experiment_id INTEGER NOT NULL, name TEXT NOT NULL,
  order_index INTEGER NOT NULL,
  FOREIGN KEY (experiment_id) REFERENCES experiment(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS marker_label (
  id INTEGER PRIMARY KEY, experiment_id INTEGER NOT NULL, label TEXT NOT NULL,
  FOREIGN KEY (experiment_id) REFERENCES experiment(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS participant (
  id INTEGER PRIMARY KEY, experiment_id INTEGER NOT NULL, code TEXT NOT NULL,
  notes TEXT DEFAULT '', created_at REAL NOT NULL,
  UNIQUE (experiment_id, code),
  FOREIGN KEY (experiment_id) REFERENCES experiment(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS session (
  id INTEGER PRIMARY KEY, experiment_id INTEGER NOT NULL, participant_id INTEGER NOT NULL,
  started_at REAL NOT NULL, notes TEXT DEFAULT '',
  FOREIGN KEY (experiment_id) REFERENCES experiment(id) ON DELETE CASCADE,
  FOREIGN KEY (participant_id) REFERENCES participant(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS recording (
  id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, condition_id INTEGER NOT NULL,
  started_at REAL NOT NULL, stopped_at REAL, csv_path TEXT NOT NULL,
  sample_count INTEGER DEFAULT 0, status TEXT NOT NULL DEFAULT 'active',
  FOREIGN KEY (session_id) REFERENCES session(id) ON DELETE CASCADE,
  FOREIGN KEY (condition_id) REFERENCES condition(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS marker (
  id INTEGER PRIMARY KEY, recording_id INTEGER NOT NULL, t_offset REAL NOT NULL,
  label TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'button',
  FOREIGN KEY (recording_id) REFERENCES recording(id) ON DELETE CASCADE);
"""


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)
            if c.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0:
                c.execute("INSERT INTO schema_version (version) VALUES (1)")

    def _conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    # ---- experiments -------------------------------------------------------
    def create_experiment(self, name, description=""):
        with self._conn() as c:
            cur = c.execute("INSERT INTO experiment (name, description, created_at) VALUES (?,?,?)",
                            (name, description, time.time()))
            return cur.lastrowid

    def list_experiments(self):
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM experiment ORDER BY created_at DESC")]

    def get_experiment(self, exp_id):
        with self._conn() as c:
            row = c.execute("SELECT * FROM experiment WHERE id=?", (exp_id,)).fetchone()
            if row is None:
                return None
            out = dict(row)
            out["conditions"] = [dict(r) for r in c.execute(
                "SELECT * FROM condition WHERE experiment_id=? ORDER BY order_index", (exp_id,))]
            out["marker_labels"] = [dict(r) for r in c.execute(
                "SELECT * FROM marker_label WHERE experiment_id=? ORDER BY id", (exp_id,))]
            return out

    def update_experiment(self, exp_id, name, description):
        with self._conn() as c:
            c.execute("UPDATE experiment SET name=?, description=? WHERE id=?",
                      (name, description, exp_id))

    def delete_experiment(self, exp_id):
        with self._conn() as c:
            c.execute("DELETE FROM experiment WHERE id=?", (exp_id,))

    def set_conditions(self, exp_id, names):
        with self._conn() as c:
            c.execute("DELETE FROM condition WHERE experiment_id=?", (exp_id,))
            for i, name in enumerate(names):
                c.execute("INSERT INTO condition (experiment_id, name, order_index) VALUES (?,?,?)",
                          (exp_id, name, i))

    def set_marker_labels(self, exp_id, labels):
        with self._conn() as c:
            c.execute("DELETE FROM marker_label WHERE experiment_id=?", (exp_id,))
            for label in labels:
                c.execute("INSERT INTO marker_label (experiment_id, label) VALUES (?,?)",
                          (exp_id, label))

    # ---- participants ------------------------------------------------------
    def create_participant(self, exp_id, code, notes=""):
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO participant (experiment_id, code, notes, created_at) VALUES (?,?,?,?)",
                (exp_id, code, notes, time.time()))
            return cur.lastrowid

    def list_participants(self, exp_id):
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM participant WHERE experiment_id=? ORDER BY code", (exp_id,))]

    def update_participant(self, pid, code, notes):
        with self._conn() as c:
            c.execute("UPDATE participant SET code=?, notes=? WHERE id=?", (code, notes, pid))

    def delete_participant(self, pid):
        with self._conn() as c:
            c.execute("DELETE FROM participant WHERE id=?", (pid,))

    # ---- sessions / recordings / markers -----------------------------------
    def create_session(self, exp_id, participant_id, notes=""):
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO session (experiment_id, participant_id, started_at, notes) VALUES (?,?,?,?)",
                (exp_id, participant_id, time.time(), notes))
            return cur.lastrowid

    def list_sessions(self, exp_id):
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM session WHERE experiment_id=? ORDER BY started_at DESC", (exp_id,))]

    def create_recording(self, session_id, condition_id, csv_path):
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO recording (session_id, condition_id, started_at, csv_path) VALUES (?,?,?,?)",
                (session_id, condition_id, time.time(), csv_path))
            return cur.lastrowid

    def finalize_recording(self, rec_id, sample_count, status="completed"):
        with self._conn() as c:
            c.execute("UPDATE recording SET stopped_at=?, sample_count=?, status=? WHERE id=?",
                      (time.time(), sample_count, status, rec_id))

    def list_recordings(self, session_id):
        with self._conn() as c:
            out = []
            for r in c.execute("SELECT * FROM recording WHERE session_id=? ORDER BY started_at",
                               (session_id,)):
                d = dict(r)
                d["marker_count"] = c.execute(
                    "SELECT COUNT(*) FROM marker WHERE recording_id=?", (r["id"],)).fetchone()[0]
                out.append(d)
            return out

    def get_recording(self, rec_id):
        with self._conn() as c:
            row = c.execute("SELECT * FROM recording WHERE id=?", (rec_id,)).fetchone()
            if row is None:
                return None
            out = dict(row)
            out["markers"] = [dict(r) for r in c.execute(
                "SELECT * FROM marker WHERE recording_id=? ORDER BY t_offset", (rec_id,))]
            return out

    def add_marker(self, rec_id, t_offset, label, source="button"):
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO marker (recording_id, t_offset, label, source) VALUES (?,?,?,?)",
                (rec_id, t_offset, label, source))
            return cur.lastrowid

    def reconcile_active_recordings(self):
        with self._conn() as c:
            cur = c.execute("UPDATE recording SET status='interrupted' WHERE status='active'")
            return cur.rowcount
```

- [ ] **Step 4: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_exp_db.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/experiments/db.py hri_monitor/tests/test_exp_db.py
git commit -m "feat(experiments): sqlite schema + crud with cascades"
```

---

### Task 3: Recorder (bus subscriber → tidy CSV)

**Files:**
- Create: `hri_monitor/hub/experiments/recorder.py`
- Test: `hri_monitor/tests/test_exp_recorder.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_exp_recorder.py`:

```python
import csv

from hub.bus import MessageBus
from hub.experiments.recorder import Recorder


def read_rows(path):
    with open(path) as f:
        return list(csv.reader(f))


def test_records_tidy_rows_with_offset(tmp_path):
    bus = MessageBus()
    p = tmp_path / "rec.csv"
    r = Recorder(bus, p, start_ts=100.0)
    r.start()
    bus.publish("shimmer.gsr", {"value": 4.2})           # ts ~ now (>100)
    bus.publish("thermal.temps", {"forehead": 34.5, "left_cheek": 33.8,
                                  "right_cheek": 33.9, "nose": 32.5})
    n = r.stop()
    rows = read_rows(p)
    assert rows[0] == ["t_offset", "signal", "value"]
    signals = [row[1] for row in rows[1:]]
    assert "shimmer.gsr" in signals
    assert signals.count("thermal.forehead") == 1
    assert n == len(rows) - 1  # sample_count excludes header
    # offsets are message_ts - start_ts (positive, monotonic-ish)
    assert all(float(row[0]) >= 0 for row in rows[1:])


def test_unrecorded_topics_ignored(tmp_path):
    bus = MessageBus()
    p = tmp_path / "rec.csv"
    r = Recorder(bus, p, start_ts=0.0)
    r.start()
    bus.publish("device.status", {"device": "rgb", "status": "connected"})
    bus.publish("thermal.frame", {"frame": object()})
    n = r.stop()
    assert n == 0
    assert read_rows(p) == [["t_offset", "signal", "value"]]


def test_stop_is_idempotent(tmp_path):
    bus = MessageBus()
    r = Recorder(bus, tmp_path / "r.csv", start_ts=0.0)
    r.start()
    assert r.stop() == r.stop()  # second stop returns same count, no error
```

- [ ] **Step 2: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_exp_recorder.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `hri_monitor/hub/experiments/recorder.py`:

```python
"""Records full-rate bus samples to a tidy-long CSV (t_offset,signal,value).
Subscribes to the in-process MessageBus; buffers rows and flushes ~1 Hz."""
import csv
import threading

from .signals import RECORDED_TOPICS, sample_rows


class Recorder:
    def __init__(self, bus, csv_path, start_ts, flush_interval=1.0):
        self.bus = bus
        self.csv_path = str(csv_path)
        self.start_ts = start_ts
        self.flush_interval = flush_interval
        self._buf = []
        self._lock = threading.Lock()
        self._count = 0
        self._file = None
        self._writer = None
        self._stopped = False
        self._timer = None

    def _on_message(self, message):
        topic = message["topic"]
        if topic not in RECORDED_TOPICS:
            return
        t = message["ts"] - self.start_ts
        rows = sample_rows(topic, message["data"])
        if rows:
            with self._lock:
                for signal, value in rows:
                    self._buf.append((round(t, 4), signal, value))

    def start(self):
        self._file = open(self.csv_path, "w", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow(["t_offset", "signal", "value"])
        self._file.flush()
        self.bus.subscribe("*", self._on_message)
        self._schedule_flush()

    def _schedule_flush(self):
        if self._stopped:
            return
        self._timer = threading.Timer(self.flush_interval, self._flush_and_reschedule)
        self._timer.daemon = True
        self._timer.start()

    def _flush_and_reschedule(self):
        self._flush()
        self._schedule_flush()

    def _flush(self):
        with self._lock:
            rows, self._buf = self._buf, []
        if rows:
            self._writer.writerows(rows)
            self._file.flush()
            self._count += len(rows)

    def stop(self):
        if self._stopped:
            return self._count
        self._stopped = True
        if self._timer:
            self._timer.cancel()
        self.bus.unsubscribe("*", self._on_message)
        self._flush()
        if self._file:
            self._file.close()
            self._file = None
        return self._count
```

- [ ] **Step 4: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_exp_recorder.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/experiments/recorder.py hri_monitor/tests/test_exp_recorder.py
git commit -m "feat(experiments): bus-subscriber recorder writing tidy csv"
```

---

### Task 4: Recording controller (one active, lifecycle)

**Files:**
- Create: `hri_monitor/hub/experiments/controller.py`
- Test: `hri_monitor/tests/test_exp_controller.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_exp_controller.py`:

```python
import pytest

from hub.bus import MessageBus
from hub.experiments.controller import RecordingController
from hub.experiments.db import Database


@pytest.fixture
def setup(tmp_path):
    db = Database(tmp_path / "hri.db")
    exp = db.create_experiment("S", "")
    db.set_conditions(exp, ["Baseline"])
    cond = db.get_experiment(exp)["conditions"][0]["id"]
    part = db.create_participant(exp, "P01", "")
    ctrl = RecordingController(MessageBus(), db, tmp_path / "recordings")
    return db, ctrl, exp, part, cond


def test_start_marker_stop(setup):
    db, ctrl, exp, part, cond = setup
    res = ctrl.start(experiment_id=exp, participant_id=part, condition_id=cond)
    rec_id = res["recording_id"]
    assert ctrl.status()["recording_id"] == rec_id
    ctrl.marker("Robot error", "button")
    st = ctrl.status()
    assert st["sample_count"] >= 0 and len(st["markers"]) == 1
    ctrl.stop()
    assert ctrl.status() is None
    assert db.get_recording(rec_id)["status"] == "completed"
    assert db.get_recording(rec_id)["markers"][0]["label"] == "Robot error"


def test_only_one_active(setup):
    db, ctrl, exp, part, cond = setup
    ctrl.start(experiment_id=exp, participant_id=part, condition_id=cond)
    with pytest.raises(RuntimeError):
        ctrl.start(experiment_id=exp, participant_id=part, condition_id=cond)
    ctrl.stop()


def test_start_reuses_session_when_given(setup):
    db, ctrl, exp, part, cond = setup
    r1 = ctrl.start(experiment_id=exp, participant_id=part, condition_id=cond)
    ctrl.stop()
    r2 = ctrl.start(session_id=r1["session_id"], condition_id=cond)
    ctrl.stop()
    assert r1["session_id"] == r2["session_id"]


def test_marker_without_active_raises(setup):
    db, ctrl, exp, part, cond = setup
    with pytest.raises(RuntimeError):
        ctrl.marker("x", "button")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_exp_controller.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `hri_monitor/hub/experiments/controller.py`:

```python
"""Owns the single active recording: lifecycle + status. Thread-safe."""
import threading
import time
from pathlib import Path

from .recorder import Recorder


class RecordingController:
    def __init__(self, bus, db, recordings_dir):
        self.bus = bus
        self.db = db
        self.recordings_dir = Path(recordings_dir)
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._active = None  # dict(recording_id, session_id, condition, start_ts, recorder)
        # reconcile any recording left 'active' from a previous crash
        self.db.reconcile_active_recordings()

    def start(self, condition_id, experiment_id=None, participant_id=None, session_id=None):
        with self._lock:
            if self._active is not None:
                raise RuntimeError("a recording is already active")
            if session_id is None:
                if experiment_id is None or participant_id is None:
                    raise ValueError("need session_id or experiment_id+participant_id")
                session_id = self.db.create_session(experiment_id, participant_id)
            start_ts = time.time()
            # create the row first to get the id, then set its CSV path to <id>.csv
            rec_id = self.db.create_recording(session_id, condition_id, csv_path="")
            csv_path = self.recordings_dir / f"{rec_id}.csv"
            self._set_csv_path(rec_id, str(csv_path))
            recorder = Recorder(self.bus, csv_path, start_ts=start_ts)
            recorder.start()
            cond = self._condition_name(condition_id)
            self._active = {"recording_id": rec_id, "session_id": session_id,
                            "condition": cond, "start_ts": start_ts, "recorder": recorder}
            return {"recording_id": rec_id, "session_id": session_id}

    def marker(self, label, source="button"):
        with self._lock:
            if self._active is None:
                raise RuntimeError("no active recording")
            t = time.time() - self._active["start_ts"]
            self.db.add_marker(self._active["recording_id"], round(t, 4), label, source)

    def stop(self):
        with self._lock:
            if self._active is None:
                return None
            a = self._active
            count = a["recorder"].stop()
            self.db.finalize_recording(a["recording_id"], sample_count=count, status="completed")
            self._active = None
            return {"recording_id": a["recording_id"], "sample_count": count}

    def status(self):
        with self._lock:
            if self._active is None:
                return None
            a = self._active
            rec = self.db.get_recording(a["recording_id"])
            return {
                "recording_id": a["recording_id"],
                "session_id": a["session_id"],
                "condition": a["condition"],
                "elapsed": round(time.time() - a["start_ts"], 1),
                "sample_count": a["recorder"]._count,
                "markers": rec["markers"] if rec else [],
            }

    # ---- helpers -----------------------------------------------------------
    def _set_csv_path(self, rec_id, path):
        with self.db._conn() as c:
            c.execute("UPDATE recording SET csv_path=? WHERE id=?", (path, rec_id))

    def _condition_name(self, condition_id):
        with self.db._conn() as c:
            row = c.execute("SELECT name FROM condition WHERE id=?", (condition_id,)).fetchone()
            return row["name"] if row else None
```

- [ ] **Step 4: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_exp_controller.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/experiments/controller.py hri_monitor/tests/test_exp_controller.py
git commit -m "feat(experiments): single-active recording controller"
```

---

### Task 5: Export helpers (CSV + session zip)

**Files:**
- Create: `hri_monitor/hub/experiments/export.py`
- Test: `hri_monitor/tests/test_exp_export.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_exp_export.py`:

```python
import io
import zipfile

from hub.experiments.db import Database
from hub.experiments.export import session_zip_bytes


def test_session_zip_contains_csvs_and_manifest(tmp_path):
    db = Database(tmp_path / "hri.db")
    exp = db.create_experiment("S", "")
    db.set_conditions(exp, ["Baseline"])
    cond = db.get_experiment(exp)["conditions"][0]["id"]
    part = db.create_participant(exp, "P01", "")
    sess = db.create_session(exp, part)
    csv1 = tmp_path / "1.csv"
    csv1.write_text("t_offset,signal,value\n0.0,shimmer.gsr,4.2\n")
    rec = db.create_recording(sess, cond, str(csv1))
    db.finalize_recording(rec, sample_count=1)
    blob = session_zip_bytes(db, sess)
    z = zipfile.ZipFile(io.BytesIO(blob))
    names = z.namelist()
    assert "session.json" in names
    assert "manifest.csv" in names
    assert any(n.endswith(".csv") and "recording" in n for n in names)
    assert b"shimmer.gsr" in z.read([n for n in names if n.startswith("recordings/")][0])
```

- [ ] **Step 2: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_exp_export.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `hri_monitor/hub/experiments/export.py`:

```python
"""Build a session export .zip: each recording's CSV + session.json + manifest.csv."""
import io
import json
import os
import zipfile


def session_zip_bytes(db, session_id) -> bytes:
    with db._conn() as c:
        sess = c.execute("SELECT * FROM session WHERE id=?", (session_id,)).fetchone()
        if sess is None:
            raise ValueError(f"session {session_id} not found")
        exp = db.get_experiment(sess["experiment_id"])
        part = c.execute("SELECT * FROM participant WHERE id=?", (sess["participant_id"],)).fetchone()
    recordings = db.list_recordings(session_id)
    cond_name = {cond["id"]: cond["name"] for cond in exp["conditions"]}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        manifest = ["recording_id,condition,started_at,sample_count,csv"]
        for rec in recordings:
            arc = f"recordings/recording_{rec['id']}.csv"
            if rec["csv_path"] and os.path.exists(rec["csv_path"]):
                z.write(rec["csv_path"], arc)
            manifest.append(
                f"{rec['id']},{cond_name.get(rec['condition_id'], '')},{rec['started_at']},{rec['sample_count']},{arc}")
        z.writestr("manifest.csv", "\n".join(manifest) + "\n")
        meta = {
            "experiment": {"id": exp["id"], "name": exp["name"], "description": exp["description"]},
            "participant": {"code": part["code"], "notes": part["notes"]} if part else None,
            "conditions": exp["conditions"],
            "recordings": [
                {"id": rec["id"], "condition": cond_name.get(rec["condition_id"], ""),
                 "started_at": rec["started_at"], "stopped_at": rec["stopped_at"],
                 "sample_count": rec["sample_count"], "status": rec["status"],
                 "markers": db.get_recording(rec["id"])["markers"]}
                for rec in recordings
            ],
        }
        z.writestr("session.json", json.dumps(meta, indent=2))
    return buf.getvalue()
```

- [ ] **Step 4: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_exp_export.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/experiments/export.py hri_monitor/tests/test_exp_export.py
git commit -m "feat(experiments): session zip export"
```

---

### Task 6: REST API router

**Files:**
- Create: `hri_monitor/hub/experiments/router.py`
- Modify: `hri_monitor/hub/server.py`
- Modify: `hri_monitor/run.py`
- Test: `hri_monitor/tests/test_exp_api.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_exp_api.py`:

```python
from fastapi.testclient import TestClient

from hub.bus import MessageBus
from hub.experiments.controller import RecordingController
from hub.experiments.db import Database
from hub.experiments.router import build_router
from fastapi import FastAPI


def make_client(tmp_path):
    db = Database(tmp_path / "hri.db")
    bus = MessageBus()
    ctrl = RecordingController(bus, db, tmp_path / "recordings")
    app = FastAPI()
    app.include_router(build_router(db, ctrl))
    return db, ctrl, TestClient(app)


def test_experiment_crud_and_conditions(tmp_path):
    _, _, client = make_client(tmp_path)
    r = client.post("/api/experiments", json={"name": "Trust", "description": "d"})
    exp = r.json()["id"]
    client.put(f"/api/experiments/{exp}/conditions", json={"conditions": ["Baseline", "Transparent"]})
    client.put(f"/api/experiments/{exp}/marker-labels", json={"labels": ["Robot error"]})
    got = client.get(f"/api/experiments/{exp}").json()
    assert got["name"] == "Trust"
    assert [c["name"] for c in got["conditions"]] == ["Baseline", "Transparent"]
    assert got["marker_labels"][0]["label"] == "Robot error"


def test_participants(tmp_path):
    _, _, client = make_client(tmp_path)
    exp = client.post("/api/experiments", json={"name": "S"}).json()["id"]
    p = client.post(f"/api/experiments/{exp}/participants", json={"code": "P01", "notes": ""})
    assert p.status_code == 200
    lst = client.get(f"/api/experiments/{exp}/participants").json()
    assert lst[0]["code"] == "P01"


def test_recording_lifecycle_and_export(tmp_path):
    db, _, client = make_client(tmp_path)
    exp = client.post("/api/experiments", json={"name": "S"}).json()["id"]
    client.put(f"/api/experiments/{exp}/conditions", json={"conditions": ["Baseline"]})
    cond = client.get(f"/api/experiments/{exp}").json()["conditions"][0]["id"]
    part = client.post(f"/api/experiments/{exp}/participants", json={"code": "P01"}).json()["id"]
    started = client.post("/api/recordings/start",
                          json={"experiment_id": exp, "participant_id": part, "condition_id": cond})
    rec = started.json()["recording_id"]
    assert client.get("/api/recordings/active").json()["recording_id"] == rec
    client.post(f"/api/recordings/{rec}/marker", json={"label": "Robot error", "source": "button"})
    client.post(f"/api/recordings/{rec}/stop")
    assert client.get("/api/recordings/active").json() is None
    # export csv
    exp_csv = client.get(f"/api/recordings/{rec}/export.csv")
    assert exp_csv.status_code == 200 and "t_offset" in exp_csv.text
    # second start while active rejected
    client.post("/api/recordings/start", json={"experiment_id": exp, "participant_id": part, "condition_id": cond})
    dup = client.post("/api/recordings/start", json={"experiment_id": exp, "participant_id": part, "condition_id": cond})
    assert dup.status_code == 409
    client.post(f"/api/recordings/{client.get('/api/recordings/active').json()['recording_id']}/stop")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_exp_api.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the router**

Create `hri_monitor/hub/experiments/router.py`:

```python
"""FastAPI routes for experiments/participants/recordings/export."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from .export import session_zip_bytes


class ExperimentIn(BaseModel):
    name: str
    description: str = ""

class NamesIn(BaseModel):
    conditions: list[str] = []

class LabelsIn(BaseModel):
    labels: list[str] = []

class ParticipantIn(BaseModel):
    code: str
    notes: str = ""

class StartIn(BaseModel):
    condition_id: int
    experiment_id: int | None = None
    participant_id: int | None = None
    session_id: int | None = None

class MarkerIn(BaseModel):
    label: str
    source: str = "button"


def build_router(db, controller) -> APIRouter:
    r = APIRouter()

    @r.get("/api/experiments")
    def list_experiments():
        return db.list_experiments()

    @r.post("/api/experiments")
    def create_experiment(body: ExperimentIn):
        return {"id": db.create_experiment(body.name, body.description)}

    @r.get("/api/experiments/{exp_id}")
    def get_experiment(exp_id: int):
        e = db.get_experiment(exp_id)
        return e if e else JSONResponse({"error": "not found"}, status_code=404)

    @r.patch("/api/experiments/{exp_id}")
    def update_experiment(exp_id: int, body: ExperimentIn):
        db.update_experiment(exp_id, body.name, body.description)
        return {"ok": True}

    @r.delete("/api/experiments/{exp_id}")
    def delete_experiment(exp_id: int):
        db.delete_experiment(exp_id)
        return {"ok": True}

    @r.put("/api/experiments/{exp_id}/conditions")
    def set_conditions(exp_id: int, body: NamesIn):
        db.set_conditions(exp_id, body.conditions)
        return {"ok": True}

    @r.put("/api/experiments/{exp_id}/marker-labels")
    def set_marker_labels(exp_id: int, body: LabelsIn):
        db.set_marker_labels(exp_id, body.labels)
        return {"ok": True}

    @r.get("/api/experiments/{exp_id}/participants")
    def list_participants(exp_id: int):
        return db.list_participants(exp_id)

    @r.post("/api/experiments/{exp_id}/participants")
    def create_participant(exp_id: int, body: ParticipantIn):
        return {"id": db.create_participant(exp_id, body.code, body.notes)}

    @r.patch("/api/participants/{pid}")
    def update_participant(pid: int, body: ParticipantIn):
        db.update_participant(pid, body.code, body.notes)
        return {"ok": True}

    @r.delete("/api/participants/{pid}")
    def delete_participant(pid: int):
        db.delete_participant(pid)
        return {"ok": True}

    @r.get("/api/experiments/{exp_id}/sessions")
    def list_sessions(exp_id: int):
        out = []
        for s in db.list_sessions(exp_id):
            s["recordings"] = db.list_recordings(s["id"])
            out.append(s)
        return out

    @r.post("/api/recordings/start")
    def start_recording(body: StartIn):
        try:
            return controller.start(condition_id=body.condition_id,
                                    experiment_id=body.experiment_id,
                                    participant_id=body.participant_id,
                                    session_id=body.session_id)
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=409)

    @r.post("/api/recordings/{rec_id}/marker")
    def add_marker(rec_id: int, body: MarkerIn):
        try:
            controller.marker(body.label, body.source)
            return {"ok": True}
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=409)

    @r.post("/api/recordings/{rec_id}/stop")
    def stop_recording(rec_id: int):
        return controller.stop() or {"ok": True}

    @r.get("/api/recordings/active")
    def active_recording():
        return controller.status()

    @r.get("/api/recordings/{rec_id}")
    def get_recording(rec_id: int):
        rec = db.get_recording(rec_id)
        return rec if rec else JSONResponse({"error": "not found"}, status_code=404)

    @r.get("/api/recordings/{rec_id}/export.csv")
    def export_csv(rec_id: int):
        rec = db.get_recording(rec_id)
        if not rec or not rec["csv_path"]:
            return JSONResponse({"error": "not found"}, status_code=404)
        with open(rec["csv_path"]) as f:
            data = f.read()
        return Response(data, media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="recording_{rec_id}.csv"'})

    @r.get("/api/sessions/{session_id}/export.zip")
    def export_zip(session_id: int):
        blob = session_zip_bytes(db, session_id)
        return Response(blob, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="session_{session_id}.zip"'})

    return r
```

- [ ] **Step 4: Wire into the app**

In `hri_monitor/hub/server.py`, change the signature and mount the router. Add params to `create_app` and include the router BEFORE the static mount. The current signature is `def create_app(bus, manager, ui_dir=None, config_path="config.yaml") -> FastAPI:`. Change to:

```python
def create_app(bus, manager, ui_dir=None, config_path="config.yaml", experiments=None) -> FastAPI:
```

Right after `app.state.frames = frames` near the top of `create_app`, add:

```python
    if experiments is not None:
        from .experiments.router import build_router
        app.include_router(build_router(experiments["db"], experiments["controller"]))
        app.state.recording_controller = experiments["controller"]
```

(The router defines `/api/...` routes which, like the other `/api` routes, are registered before the `StaticFiles` mount at the end of `create_app`, so they are not shadowed.)

- [ ] **Step 5: Wire into run.py**

In `hri_monitor/run.py`, after `manager = SensorManager(bus, config)` and before `app = create_app(...)`, add:

```python
    from hub.experiments.controller import RecordingController
    from hub.experiments.db import Database
    data_dir = ROOT / config.get("data_dir", "data")
    exp_db = Database(data_dir / "hri.db")
    rec_ctrl = RecordingController(bus, exp_db, data_dir / "recordings")
    experiments = {"db": exp_db, "controller": rec_ctrl}
```

Change the `create_app(...)` call to pass `experiments=experiments`:

```python
    app = create_app(bus, manager, ui_dir=ROOT / "ui_dist",
                     config_path=ROOT / "config.yaml", experiments=experiments)
```

- [ ] **Step 6: Run to verify pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_exp_api.py -v`
Expected: 3 passed. Then full suite: `.venv/bin/python -m pytest tests -q` → all pass (58 + new). Confirm the existing server tests still pass (create_app's new optional param defaults to None, so milestone-1/2 tests that call `create_app(bus, FakeManager())` are unaffected).

- [ ] **Step 7: Commit**

```bash
git add hri_monitor/hub/experiments/router.py hri_monitor/hub/server.py hri_monitor/run.py hri_monitor/tests/test_exp_api.py
git commit -m "feat(experiments): rest api router wired into app + run.py"
```

---

### Task 7: Active-status shape + backend regression

The UI polls `GET /api/recordings/active` (1 Hz) for the timer/sample-counter, so no WebSocket change is needed — this task is verification only.

**Files:**
- Test: `hri_monitor/tests/test_exp_api.py` (append a status-shape test)

- [ ] **Step 1: Append a status-shape test**

Append to `hri_monitor/tests/test_exp_api.py`:

```python
def test_active_status_shape(tmp_path):
    db, ctrl, client = make_client(tmp_path)
    exp = client.post("/api/experiments", json={"name": "S"}).json()["id"]
    client.put(f"/api/experiments/{exp}/conditions", json={"conditions": ["Baseline"]})
    cond = client.get(f"/api/experiments/{exp}").json()["conditions"][0]["id"]
    part = client.post(f"/api/experiments/{exp}/participants", json={"code": "P01"}).json()["id"]
    rec = client.post("/api/recordings/start",
                      json={"experiment_id": exp, "participant_id": part, "condition_id": cond}).json()["recording_id"]
    st = client.get("/api/recordings/active").json()
    assert st["recording_id"] == rec
    assert st["condition"] == "Baseline"
    assert "elapsed" in st and "sample_count" in st and "markers" in st
    client.post(f"/api/recordings/{rec}/stop")
```

- [ ] **Step 2: Run to verify it passes**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_exp_api.py -v`
Expected: all pass. (No server change needed — the UI polls `GET /api/recordings/active` for the timer/counter; the spec's WS push is an optimization the UI plan does not depend on. We rely on polling, keeping this task test-only. Note this decision in the commit.)

- [ ] **Step 3: Full regression**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests -q`
Expected: all pass. Report the exact count (58 baseline + signals 5 + db 5 + recorder 3 + controller 4 + export 1 + api 4 = 80).

- [ ] **Step 4: Simulator-mode smoke (records real bus data)**

```bash
cd hri_monitor && .venv/bin/python run.py --no-browser & sleep 4
EXP=$(curl -s -X POST http://127.0.0.1:8000/api/experiments -H 'Content-Type: application/json' -d '{"name":"Smoke"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X PUT http://127.0.0.1:8000/api/experiments/$EXP/conditions -H 'Content-Type: application/json' -d '{"conditions":["Baseline"]}' >/dev/null
COND=$(curl -s http://127.0.0.1:8000/api/experiments/$EXP | python3 -c "import sys,json;print(json.load(sys.stdin)['conditions'][0]['id'])")
PART=$(curl -s -X POST http://127.0.0.1:8000/api/experiments/$EXP/participants -H 'Content-Type: application/json' -d '{"code":"P01"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
REC=$(curl -s -X POST http://127.0.0.1:8000/api/recordings/start -H 'Content-Type: application/json' -d "{\"experiment_id\":$EXP,\"participant_id\":$PART,\"condition_id\":$COND}" | python3 -c "import sys,json;print(json.load(sys.stdin)['recording_id'])")
sleep 3
curl -s -X POST http://127.0.0.1:8000/api/recordings/$REC/marker -H 'Content-Type: application/json' -d '{"label":"test","source":"button"}' >/dev/null
curl -s -X POST http://127.0.0.1:8000/api/recordings/$REC/stop >/dev/null
echo "--- recorded CSV (first lines) ---"; head -5 data/recordings/$REC.csv
kill %1
git checkout config.yaml 2>/dev/null || true
```

Expected: the CSV has the `t_offset,signal,value` header and rows from the simulators (`shimmer.gsr`, `thermal.forehead`, etc.) accumulated over ~3 s. Report the row count.

- [ ] **Step 5: Confirm data/ is gitignored, commit**

```bash
git status --short   # data/ must NOT appear (gitignored from milestone 1)
git add hri_monitor/tests/test_exp_api.py
git commit -m "test(experiments): active-status shape; backend complete"
```

Report backend milestone complete; the UI plan (`2026-06-16-experiments-ui.md`) is next.
