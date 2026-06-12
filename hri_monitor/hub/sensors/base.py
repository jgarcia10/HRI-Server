import logging
import threading
import time

log = logging.getLogger(__name__)


class BaseSensor:
    """Sensor lifecycle: a daemon thread that connects, reads in a loop, and
    reconnects with exponential backoff on any failure or when samples go
    stale. Subclasses implement connect()/read()/disconnect(); read() must
    call self.emit() for every sample and return quickly (< ~100 ms).

    Status values: disabled, connecting, connected, reconnecting. Every
    transition is published on the bus as topic "device.status" with data
    {"device": <name>, "status": <status>}.
    """

    name = "base"
    stale_after = 5.0
    initial_backoff = 1.0
    max_backoff = 30.0

    def __init__(self, bus):
        self.bus = bus
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_emit = 0.0
        self._status = "disabled"

    # ---- subclass contract --------------------------------------------------
    def connect(self):
        raise NotImplementedError

    def read(self):
        raise NotImplementedError

    def disconnect(self):
        pass

    # ---- public API -----------------------------------------------------------
    @property
    def status(self) -> str:
        return self._status

    def emit(self, topic: str, data) -> None:
        self._last_emit = time.monotonic()
        self.bus.publish(topic, data)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"sensor-{self.name}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._set_status("disabled")

    # ---- internals ------------------------------------------------------------
    def _set_status(self, status: str) -> None:
        if status != self._status:
            self._status = status
            self.bus.publish("device.status", {"device": self.name, "status": status})

    def _safe_disconnect(self) -> None:
        try:
            self.disconnect()
        except Exception:
            log.exception("%s: disconnect failed", self.name)

    def _run(self) -> None:
        backoff = self.initial_backoff
        first = True
        while not self._stop.is_set():
            try:
                self._set_status("connecting" if first else "reconnecting")
                first = False
                self.connect()
                self._set_status("connected")
                backoff = self.initial_backoff
                self._last_emit = time.monotonic()
                while not self._stop.is_set():
                    self.read()
                    if time.monotonic() - self._last_emit > self.stale_after:
                        raise TimeoutError(f"no samples for {self.stale_after}s")
            except Exception as exc:
                log.warning("%s: %s — reconnecting in %.1fs", self.name, exc, backoff)
                self._safe_disconnect()
                self._set_status("reconnecting")
                self._stop.wait(backoff)
                backoff = min(backoff * 2, self.max_backoff)
        self._safe_disconnect()
        self._set_status("disabled")
