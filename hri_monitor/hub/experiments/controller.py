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

    def _set_csv_path(self, rec_id, path):
        with self.db._conn() as c:
            c.execute("UPDATE recording SET csv_path=? WHERE id=?", (path, rec_id))

    def _condition_name(self, condition_id):
        with self.db._conn() as c:
            row = c.execute("SELECT name FROM condition WHERE id=?", (condition_id,)).fetchone()
            return row["name"] if row else None
