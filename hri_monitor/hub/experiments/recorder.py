"""Records full-rate bus samples to a tidy-long CSV (t_offset,signal,value).
Subscribes to the in-process MessageBus; buffers rows and flushes ~1 Hz."""
import csv
import logging
import threading

from .signals import RECORDED_TOPICS, sample_rows

log = logging.getLogger(__name__)


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
        try:
            rows = sample_rows(topic, message["data"])
        except Exception:
            log.warning("recorder: bad payload on %s, skipped", topic)
            return
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

    def _drain_locked(self):
        """Write buffered rows to the CSV. Caller MUST hold self._lock."""
        if self._file is None:
            return
        rows, self._buf = self._buf, []
        if not rows:
            return
        try:
            self._writer.writerows(rows)
            self._file.flush()
            self._count += len(rows)
        except Exception:
            log.exception("recorder: csv write failed (%d rows lost)", len(rows))

    def _flush(self):
        with self._lock:
            self._drain_locked()

    def stop(self):
        if self._stopped:
            return self._count
        self._stopped = True
        if self._timer:
            self._timer.cancel()
        self.bus.unsubscribe("*", self._on_message)
        with self._lock:
            self._drain_locked()
            if self._file:
                self._file.close()
                self._file = None
        return self._count
