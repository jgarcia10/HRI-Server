"""Hub-side proxy for the isolated Optris thermal worker subprocess. The proxy
is a BaseSensor; connect() spawns the worker, read() emits framed messages."""
import os
import select
import subprocess
import sys
import time

from .base import BaseSensor
from .thermal_codec import read_message


class ThermalProcess(BaseSensor):
    name = "thermal"
    read_timeout = 10.0
    stale_after = 8.0

    def __init__(self, bus, xml=None, detector=None, predictor=None, format_dir="/tmp/optris"):
        super().__init__(bus)
        self.xml = xml
        self.detector = detector
        self.predictor = predictor
        self.format_dir = format_dir
        self._proc = None
        self._stdout = None

    def _read_message_timed(self, timeout):
        """Read one framed message, raising TimeoutError if the worker produces
        nothing within `timeout`. Polls in <=1s slices so stop() stays responsive."""
        fd = self._stdout.fileno()
        end = time.monotonic() + timeout
        while True:
            if self._stop.is_set():
                raise RuntimeError("stopping")
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"thermal worker silent for {timeout}s — assuming wedged")
            r, _, _ = select.select([fd], [], [], min(remaining, 1.0))
            if r:
                break
        msg = read_message(self._stdout)
        if msg is None:
            raise RuntimeError("thermal worker died (pipe EOF)")
        return msg

    def connect(self):
        for label, path in [("xml", self.xml), ("detector", self.detector), ("predictor", self.predictor)]:
            if not path or not os.path.exists(path):
                raise RuntimeError(f"thermal asset not found ({label}): {path}")
        os.makedirs(self.format_dir, exist_ok=True)
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "hub.sensors.thermal_worker",
             "--xml", self.xml, "--detector", self.detector,
             "--predictor", self.predictor, "--format-dir", self.format_dir],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._stdout = self._proc.stdout
        try:
            first = self._read_message_timed(self.read_timeout)
        except Exception:
            err = self._proc.stderr.read().decode("utf-8", "replace")[-300:] if self._proc.stderr else ""
            self.disconnect()
            raise RuntimeError(f"thermal worker failed to start: {err}")
        self._emit_message(first)

    def read(self):
        msg = self._read_message_timed(self.read_timeout)
        self._emit_message(msg)

    def _emit_message(self, msg):
        temps, frame = msg
        self.emit("thermal.temps", temps)
        self.emit("thermal.frame", {"frame": frame})

    def disconnect(self):
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
            self._stdout = None
