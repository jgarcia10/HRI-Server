"""SQLite metadata store for experiments/participants/sessions/recordings/markers.
Stdlib sqlite3 only. One Database instance per process; methods are short-lived
connections so they are safe to call from multiple threads."""
import os
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
            paths = [r["csv_path"] for r in c.execute(
                "SELECT r.csv_path FROM recording r "
                "JOIN session s ON r.session_id = s.id WHERE s.experiment_id=?", (exp_id,))]
            c.execute("DELETE FROM experiment WHERE id=?", (exp_id,))
        self._unlink_csvs(paths)

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
            paths = [r["csv_path"] for r in c.execute(
                "SELECT r.csv_path FROM recording r "
                "JOIN session s ON r.session_id = s.id WHERE s.participant_id=?", (pid,))]
            c.execute("DELETE FROM participant WHERE id=?", (pid,))
        self._unlink_csvs(paths)

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

    def get_session(self, session_id):
        with self._conn() as c:
            row = c.execute("SELECT * FROM session WHERE id=?", (session_id,)).fetchone()
            return dict(row) if row else None

    def delete_session(self, session_id):
        """Delete a whole run: its recordings + markers cascade; remove their CSVs."""
        with self._conn() as c:
            paths = [r["csv_path"] for r in c.execute(
                "SELECT csv_path FROM recording WHERE session_id=?", (session_id,))]
            c.execute("DELETE FROM session WHERE id=?", (session_id,))
        self._unlink_csvs(paths)

    def delete_recording(self, rec_id):
        """Delete one recording (condition run): its markers cascade; remove its CSV."""
        with self._conn() as c:
            row = c.execute("SELECT csv_path FROM recording WHERE id=?", (rec_id,)).fetchone()
            paths = [row["csv_path"]] if row else []
            c.execute("DELETE FROM recording WHERE id=?", (rec_id,))
        self._unlink_csvs(paths)

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

    def recordings_for_conditions(self, experiment_id, condition_ids):
        """All recordings of the given conditions in the experiment, with participant."""
        if not condition_ids:
            return []
        qs = ",".join("?" * len(condition_ids))
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                f"SELECT r.id, r.condition_id, r.csv_path, s.participant_id "
                f"FROM recording r JOIN session s ON r.session_id = s.id "
                f"WHERE s.experiment_id=? AND r.condition_id IN ({qs})",
                (experiment_id, *condition_ids))]

    def recordings_for_experiment(self, experiment_id):
        """All recordings of the experiment (every condition), with participant."""
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT r.id, r.condition_id, r.csv_path, s.participant_id "
                "FROM recording r JOIN session s ON r.session_id = s.id "
                "WHERE s.experiment_id=?", (experiment_id,))]

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

    def _unlink_csvs(self, paths):
        """Best-effort delete of recording CSV files on disk."""
        for p in paths:
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass
