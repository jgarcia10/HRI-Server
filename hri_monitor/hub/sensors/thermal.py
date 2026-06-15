"""Hub-side proxy for the isolated Optris thermal worker subprocess. The proxy
is a BaseSensor; connect() spawns the worker, read() emits framed messages."""
import os
import select
import subprocess
import sys
import time

from ..assets import HRI_ROOT, resolve_asset
from .base import BaseSensor
from .thermal_codec import read_message


def _drain_stderr(proc) -> str:
    """Read whatever is already buffered on the worker's stderr WITHOUT blocking
    on EOF (the worker may be wedged in an uninterruptible syscall)."""
    if proc is None or proc.stderr is None:
        return ""
    try:
        fd = proc.stderr.fileno()
        os.set_blocking(fd, False)
        data = b""
        while True:
            try:
                chunk = os.read(fd, 4096)
            except BlockingIOError:
                break
            if not chunk:
                break
            data += chunk
        return data.decode("utf-8", "replace")[-300:]
    except Exception:  # noqa: BLE001
        return ""


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
        # Resolve asset paths against cwd / hri_monitor / repo root, since the
        # dlib models + calibration XML usually live at the repo root.
        resolved = {}
        for label in ("xml", "detector", "predictor"):
            raw = getattr(self, label)
            path = resolve_asset(raw)
            if path is None:
                raise RuntimeError(
                    f"thermal asset not found ({label}): {raw!r} — put it at the repo "
                    f"root or set an absolute path in the Devices page / config.yaml")
            resolved[label] = path
        os.makedirs(self.format_dir, exist_ok=True)
        # Dedicated pipe for the binary frame protocol — keeps it clean from the
        # Optris SDK / dlib / OpenCV logging that pollutes the worker's stdout.
        frame_r, frame_w = os.pipe()
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "hub.sensors.thermal_worker",
             "--xml", resolved["xml"], "--detector", resolved["detector"],
             "--predictor", resolved["predictor"], "--format-dir", self.format_dir,
             "--out-fd", str(frame_w)],
            cwd=HRI_ROOT,  # so the worker can import `hub` regardless of launch dir
            pass_fds=(frame_w,),
            stdout=subprocess.DEVNULL,  # SDK/library banner noise — discarded
            stderr=subprocess.PIPE)     # real errors (Formats.def, usb_init, …)
        os.close(frame_w)  # parent keeps only the read end
        self._stdout = os.fdopen(frame_r, "rb", buffering=0)
        try:
            first = self._read_message_timed(self.read_timeout)
        except Exception as exc:
            # Grab whatever the worker already wrote to stderr (the SDK error),
            # then kill it. Both are non-blocking: a worker wedged in an
            # uninterruptible SDK/USB syscall (e.g. no camera) can't be reaped
            # promptly, so we must not block reading its stderr to EOF.
            err = _drain_stderr(self._proc)
            self.disconnect()
            raise RuntimeError(f"thermal worker failed to start: {err or exc}")
        self._emit_message(first)

    def read(self):
        msg = self._read_message_timed(self.read_timeout)
        self._emit_message(msg)

    def _emit_message(self, msg):
        temps, frame = msg
        self.emit("thermal.temps", temps)
        self.emit("thermal.frame", {"frame": frame})

    def disconnect(self):
        if self._stdout is not None:
            try:
                self._stdout.close()  # close the frame-pipe read end
            except Exception:  # noqa: BLE001
                pass
            self._stdout = None
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
