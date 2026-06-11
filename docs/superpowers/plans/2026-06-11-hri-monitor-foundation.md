# HRI Monitor — Plan 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A runnable `hri_monitor/` platform: message bus, watchdog-supervised simulated sensors (Shimmer GSR/PPG, thermal, RGB), FastAPI hub (WebSocket telemetry, MJPEG streams, status API), single `run.py` entry point, and a dark sidebar React UI with a working Live page — all demoable with zero hardware.

**Architecture:** One ROS-free hub process (spec §2, option B). Sensors are threads inheriting a watchdog base class and publishing onto an in-process pub/sub bus. FastAPI consumes the bus for `/ws` (decimated JSON) and `/stream/*` (MJPEG), and serves the pre-built React UI from `ui_dist/`. Real drivers, models, ROS adapters, experiments, and statistics land in Plans 2–6 against the interfaces built here.

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, NumPy, OpenCV, PyYAML, pytest, httpx (test client). UI: React 18 + TypeScript + Vite + Tailwind v4 + Recharts.

**Spec:** `docs/superpowers/specs/2026-06-11-hri-monitor-platform-design.md`

**Working directory for all commands:** `/home/juanjose-ensta/Documents/HRIServcer/hri_monitor` (created in Task 1). Python commands assume `source .venv/bin/activate`.

---

### Task 1: Scaffold, virtualenv, and config loader

**Files:**
- Create: `hri_monitor/requirements.txt`
- Create: `hri_monitor/config.yaml`
- Create: `hri_monitor/hub/__init__.py`, `hri_monitor/hub/sensors/__init__.py`, `hri_monitor/tests/__init__.py` (all empty)
- Create: `hri_monitor/hub/config.py`
- Test: `hri_monitor/tests/test_config.py`
- Modify: `.gitignore` (repo root)

- [ ] **Step 1: Create the skeleton and virtualenv**

```bash
cd /home/juanjose-ensta/Documents/HRIServcer
mkdir -p hri_monitor/hub/sensors hri_monitor/tests
touch hri_monitor/hub/__init__.py hri_monitor/hub/sensors/__init__.py hri_monitor/tests/__init__.py
printf '\n# HRI Monitor\nnode_modules/\nhri_monitor/data/\n' >> .gitignore
cd hri_monitor
python3 -m venv .venv
source .venv/bin/activate
```

Create `hri_monitor/requirements.txt`:

```
fastapi>=0.110
uvicorn[standard]>=0.29
numpy>=1.26
opencv-python>=4.9
PyYAML>=6.0
httpx>=0.27
pytest>=8.0
```

Run: `pip install -r requirements.txt`
Expected: all packages install without error.

- [ ] **Step 2: Write the failing config test**

Create `hri_monitor/tests/test_config.py`:

```python
from hub.config import load_config


def test_defaults_when_file_missing(tmp_path):
    cfg = load_config(tmp_path / "nope.yaml")
    assert cfg["server"]["port"] == 8000
    assert cfg["sensors"]["shimmer"]["simulate"] is True


def test_user_values_override_defaults_and_keep_the_rest(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("server:\n  port: 9001\n")
    cfg = load_config(p)
    assert cfg["server"]["port"] == 9001
    assert cfg["server"]["host"] == "127.0.0.1"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hub.config'`

- [ ] **Step 4: Implement the config loader**

Create `hri_monitor/hub/config.py`:

```python
import copy
from pathlib import Path

import yaml

DEFAULTS = {
    "server": {"host": "127.0.0.1", "port": 8000, "open_browser": True},
    "data_dir": "data",
    "sensors": {
        "shimmer": {"enabled": True, "simulate": True, "mac": None, "sampling_rate": 200},
        "thermal": {"enabled": True, "simulate": True, "xml": None},
        "rgb": {"enabled": True, "simulate": True, "index": 0, "width": 640, "height": 480, "fps": 30},
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path | str = "config.yaml") -> dict:
    path = Path(path)
    user = {}
    if path.exists():
        user = yaml.safe_load(path.read_text()) or {}
    return _merge(DEFAULTS, user)
```

Create `hri_monitor/config.yaml` (user-editable mirror of the defaults):

```yaml
# HRI Monitor configuration. Anything omitted falls back to built-in defaults.
server:
  host: 127.0.0.1
  port: 8000
  open_browser: true

data_dir: data

sensors:
  shimmer:
    enabled: true
    simulate: true     # real Shimmer driver arrives in milestone 2
    mac: null
    sampling_rate: 200
  thermal:
    enabled: true
    simulate: true     # real Optris driver arrives in milestone 2
    xml: null
  rgb:
    enabled: true
    simulate: true     # real V4L2 driver arrives in milestone 2
    index: 0
    width: 640
    height: 480
    fps: 30
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
cd /home/juanjose-ensta/Documents/HRIServcer
git add .gitignore hri_monitor/requirements.txt hri_monitor/config.yaml hri_monitor/hub hri_monitor/tests
git commit -m "feat(hri_monitor): scaffold project with config loader"
```

---

### Task 2: Message bus

**Files:**
- Create: `hri_monitor/hub/bus.py`
- Test: `hri_monitor/tests/test_bus.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_bus.py`:

```python
from hub.bus import MessageBus


def test_subscriber_receives_published_message():
    bus = MessageBus()
    got = []
    bus.subscribe("a.b", got.append)
    bus.publish("a.b", {"value": 1})
    assert len(got) == 1
    assert got[0]["topic"] == "a.b"
    assert got[0]["data"] == {"value": 1}
    assert isinstance(got[0]["ts"], float)


def test_wildcard_subscriber_receives_every_topic():
    bus = MessageBus()
    got = []
    bus.subscribe("*", got.append)
    bus.publish("x", {})
    bus.publish("y", {})
    assert [m["topic"] for m in got] == ["x", "y"]


def test_unsubscribe_stops_delivery():
    bus = MessageBus()
    got = []
    bus.subscribe("a", got.append)
    bus.unsubscribe("a", got.append)
    bus.publish("a", {})
    assert got == []


def test_crashing_subscriber_does_not_block_others():
    bus = MessageBus()
    got = []
    bus.subscribe("t", lambda m: 1 / 0)
    bus.subscribe("t", got.append)
    bus.publish("t", {"ok": True})
    assert len(got) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_bus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hub.bus'`

- [ ] **Step 3: Implement the bus**

Create `hri_monitor/hub/bus.py`:

```python
import logging
import threading
import time
from collections import defaultdict

log = logging.getLogger(__name__)


class MessageBus:
    """Thread-safe in-process pub/sub. Subscribe to '*' to receive everything.

    Messages are dicts: {"topic": str, "ts": float, "data": Any}. Callbacks run
    on the publisher's thread and must not raise (failures are logged and
    isolated so one bad subscriber cannot break the others).
    """

    def __init__(self):
        self._subs: dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, topic: str, callback) -> None:
        with self._lock:
            self._subs[topic].append(callback)

    def unsubscribe(self, topic: str, callback) -> None:
        with self._lock:
            if callback in self._subs.get(topic, []):
                self._subs[topic].remove(callback)

    def publish(self, topic: str, data) -> None:
        message = {"topic": topic, "ts": time.time(), "data": data}
        with self._lock:
            callbacks = list(self._subs.get(topic, [])) + list(self._subs.get("*", []))
        for callback in callbacks:
            try:
                callback(message)
            except Exception:
                log.exception("Bus subscriber failed for topic %s", topic)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_bus.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/bus.py hri_monitor/tests/test_bus.py
git commit -m "feat(hri_monitor): thread-safe message bus with wildcard subscription"
```

---

### Task 3: Sensor base class with watchdog

**Files:**
- Create: `hri_monitor/hub/sensors/base.py`
- Test: `hri_monitor/tests/test_sensor_base.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_sensor_base.py`:

```python
import time

from hub.bus import MessageBus
from hub.sensors.base import BaseSensor


class FlakySensor(BaseSensor):
    """First connect() fails; second succeeds and streams samples."""

    name = "flaky"
    stale_after = 1.0
    initial_backoff = 0.05

    def __init__(self, bus):
        super().__init__(bus)
        self.connect_attempts = 0

    def connect(self):
        self.connect_attempts += 1
        if self.connect_attempts == 1:
            raise ConnectionError("boom")

    def read(self):
        self.emit("flaky.value", {"value": 1})
        time.sleep(0.01)


class SilentSensor(BaseSensor):
    """Connects fine but never emits — must trip the staleness watchdog."""

    name = "silent"
    stale_after = 0.15
    initial_backoff = 10.0  # large so we observe exactly one drop

    def connect(self):
        pass

    def read(self):
        time.sleep(0.02)


def wait_for(predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_reconnects_after_failed_connect_and_streams():
    bus = MessageBus()
    samples = []
    bus.subscribe("flaky.value", samples.append)
    sensor = FlakySensor(bus)
    sensor.start()
    try:
        assert wait_for(lambda: sensor.status == "connected")
        assert sensor.connect_attempts == 2
        assert wait_for(lambda: len(samples) > 5)
    finally:
        sensor.stop()
    assert sensor.status == "disabled"


def test_stale_data_triggers_reconnect():
    bus = MessageBus()
    statuses = []
    bus.subscribe("device.status", lambda m: statuses.append(m["data"]["status"]))
    sensor = SilentSensor(bus)
    sensor.start()
    try:
        assert wait_for(lambda: "reconnecting" in statuses)
    finally:
        sensor.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sensor_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hub.sensors.base'`

- [ ] **Step 3: Implement the base sensor**

Create `hri_monitor/hub/sensors/base.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sensor_base.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/sensors/base.py hri_monitor/tests/test_sensor_base.py
git commit -m "feat(hri_monitor): watchdog-supervised sensor base class"
```

---

### Task 4: Simulated sensors (Shimmer, thermal, RGB)

**Files:**
- Create: `hri_monitor/hub/sensors/simulators.py`
- Test: `hri_monitor/tests/test_simulators.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_simulators.py`:

```python
import numpy as np

from hub.bus import MessageBus
from hub.sensors.simulators import SimulatedRGB, SimulatedShimmer, SimulatedThermal


def collect(sensor_cls, topics):
    bus = MessageBus()
    got = {t: [] for t in topics}
    for t in topics:
        bus.subscribe(t, got[t].append)
    sensor = sensor_cls(bus)
    sensor.connect()
    sensor.read()  # one synchronous iteration — no thread needed
    return got


def test_simulated_shimmer_emits_plausible_gsr_and_ppg():
    got = collect(SimulatedShimmer, ["shimmer.gsr", "shimmer.ppg"])
    gsr = got["shimmer.gsr"][0]["data"]["value"]
    ppg = got["shimmer.ppg"][0]["data"]["value"]
    assert 0.0 < gsr < 30.0
    assert 0.0 < ppg < 3000.0


def test_simulated_thermal_emits_frame_and_four_roi_temps():
    got = collect(SimulatedThermal, ["thermal.frame", "thermal.temps"])
    frame = got["thermal.frame"][0]["data"]["frame"]
    temps = got["thermal.temps"][0]["data"]
    assert isinstance(frame, np.ndarray) and frame.shape == (240, 320, 3)
    assert set(temps) == {"forehead", "left_cheek", "right_cheek", "nose"}
    assert all(25.0 < v < 40.0 for v in temps.values())


def test_simulated_rgb_emits_frame_and_blink():
    got = collect(SimulatedRGB, ["rgb.frame", "rgb.blink"])
    frame = got["rgb.frame"][0]["data"]["frame"]
    blink = got["rgb.blink"][0]["data"]
    assert isinstance(frame, np.ndarray) and frame.shape == (240, 320, 3)
    assert blink["rate"] >= 0.0
    assert 0.0 < blink["ear"] < 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_simulators.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hub.sensors.simulators'`

- [ ] **Step 3: Implement the simulators**

Create `hri_monitor/hub/sensors/simulators.py`:

```python
"""Hardware-free sensor twins. They emit the same topics and payload shapes
as the real drivers (milestone 2), so the whole pipeline runs with no devices."""
import math
import random
import time

import cv2
import numpy as np

from .base import BaseSensor


class SimulatedShimmer(BaseSensor):
    name = "shimmer"

    def connect(self):
        pass

    def read(self):
        t = time.time()
        gsr = 4.0 + 0.8 * math.sin(t / 13.0) + random.gauss(0, 0.05)
        ppg = 1500.0 + 400.0 * math.sin(2 * math.pi * 1.2 * t) + random.gauss(0, 20.0)
        self.emit("shimmer.gsr", {"value": round(gsr, 3)})
        self.emit("shimmer.ppg", {"value": round(ppg, 1)})
        time.sleep(0.04)


class SimulatedThermal(BaseSensor):
    name = "thermal"

    ROIS = {
        "forehead": (130, 50, 190, 80),
        "left_cheek": (115, 120, 145, 150),
        "right_cheek": (175, 120, 205, 150),
        "nose": (150, 110, 170, 135),
    }
    BASE_TEMPS = {"forehead": 34.5, "left_cheek": 33.8, "right_cheek": 33.9, "nose": 32.5}

    def connect(self):
        pass

    def read(self):
        t = time.time()
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:] = (60, 30, 20)
        cv2.ellipse(frame, (160, 120), (70, 90), 0, 0, 360, (40, 60, 200), -1)
        temps = {}
        for roi, (x0, y0, x1, y1) in self.ROIS.items():
            temp = self.BASE_TEMPS[roi] + 0.4 * math.sin(t / 30.0) + random.gauss(0, 0.05)
            temps[roi] = round(temp, 2)
            cv2.rectangle(frame, (x0, y0), (x1, y1), (80, 255, 80), 1)
            cv2.putText(frame, f"{temps[roi]:.1f}", (x0, y0 - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        self.emit("thermal.frame", {"frame": frame})
        self.emit("thermal.temps", temps)
        time.sleep(0.1)


class SimulatedRGB(BaseSensor):
    name = "rgb"

    def connect(self):
        pass

    def read(self):
        t = time.time()
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:] = (30, 30, 30)
        cv2.circle(frame, (int(160 + 80 * math.sin(t)), 120), 30, (200, 180, 60), -1)
        cv2.putText(frame, "simulated rgb", (10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        rate = 17.0 + 3.0 * math.sin(t / 20.0) + random.gauss(0, 0.3)
        self.emit("rgb.frame", {"frame": frame})
        self.emit("rgb.blink", {"rate": round(max(rate, 0.0), 2),
                                "ear": round(0.3 + random.gauss(0, 0.01), 3)})
        time.sleep(0.1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_simulators.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/sensors/simulators.py hri_monitor/tests/test_simulators.py
git commit -m "feat(hri_monitor): simulated shimmer, thermal and rgb sensors"
```

---

### Task 5: Sensor manager

**Files:**
- Create: `hri_monitor/hub/sensors/manager.py`
- Test: `hri_monitor/tests/test_manager.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_manager.py`:

```python
import copy

from hub.bus import MessageBus
from hub.config import DEFAULTS
from hub.sensors.manager import SensorManager


def test_manager_builds_enabled_sensors_and_reports_status():
    manager = SensorManager(MessageBus(), DEFAULTS)
    assert set(manager.sensors) == {"shimmer", "thermal", "rgb"}
    assert manager.statuses() == {"shimmer": "disabled", "thermal": "disabled", "rgb": "disabled"}


def test_manager_skips_disabled_sensors():
    cfg = copy.deepcopy(DEFAULTS)
    cfg["sensors"]["rgb"]["enabled"] = False
    manager = SensorManager(MessageBus(), cfg)
    assert "rgb" not in manager.sensors
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hub.sensors.manager'`

- [ ] **Step 3: Implement the manager**

Create `hri_monitor/hub/sensors/manager.py`:

```python
from .simulators import SimulatedRGB, SimulatedShimmer, SimulatedThermal


class SensorManager:
    """Builds sensors from config and owns their lifecycle.

    Milestone 2 will branch on cfg["simulate"] to pick real drivers; for now
    every enabled sensor gets its simulator twin.
    """

    def __init__(self, bus, config: dict):
        self.bus = bus
        self.sensors = {}
        cfg = config["sensors"]
        if cfg["shimmer"]["enabled"]:
            self.sensors["shimmer"] = SimulatedShimmer(bus)
        if cfg["thermal"]["enabled"]:
            self.sensors["thermal"] = SimulatedThermal(bus)
        if cfg["rgb"]["enabled"]:
            self.sensors["rgb"] = SimulatedRGB(bus)

    def start_all(self) -> None:
        for sensor in self.sensors.values():
            sensor.start()

    def stop_all(self) -> None:
        for sensor in self.sensors.values():
            sensor.stop()

    def statuses(self) -> dict:
        return {name: sensor.status for name, sensor in self.sensors.items()}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_manager.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/sensors/manager.py hri_monitor/tests/test_manager.py
git commit -m "feat(hri_monitor): sensor manager builds sensors from config"
```

---

### Task 6: Frame store (latest frame → JPEG)

**Files:**
- Create: `hri_monitor/hub/frames.py`
- Test: `hri_monitor/tests/test_frames.py`

- [ ] **Step 1: Write the failing test**

Create `hri_monitor/tests/test_frames.py`:

```python
import numpy as np

from hub.bus import MessageBus
from hub.frames import FrameStore


def test_frame_store_returns_jpeg_of_latest_frame():
    bus = MessageBus()
    store = FrameStore(bus, {"thermal": "thermal.frame"})
    assert store.has("thermal") and not store.has("nope")
    assert store.jpeg("thermal") is None
    bus.publish("thermal.frame", {"frame": np.zeros((10, 10, 3), dtype=np.uint8)})
    jpg = store.jpeg("thermal")
    assert jpg is not None and jpg[:2] == b"\xff\xd8"  # JPEG magic bytes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_frames.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hub.frames'`

- [ ] **Step 3: Implement the frame store**

Create `hri_monitor/hub/frames.py`:

```python
import threading

import cv2


class FrameStore:
    """Keeps the latest raw frame per named feed and encodes JPEG on demand.

    feeds maps a public feed name to a bus topic whose payload is
    {"frame": np.ndarray}, e.g. {"thermal": "thermal.frame"}.
    """

    def __init__(self, bus, feeds: dict):
        self._feeds = dict(feeds)
        self._frames = {}
        self._lock = threading.Lock()
        for feed, topic in self._feeds.items():
            bus.subscribe(topic, self._make_handler(feed))

    def _make_handler(self, feed: str):
        def handler(message):
            with self._lock:
                self._frames[feed] = message["data"]["frame"]
        return handler

    def has(self, feed: str) -> bool:
        return feed in self._feeds

    def jpeg(self, feed: str) -> bytes | None:
        with self._lock:
            frame = self._frames.get(feed)
        if frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame)
        return buf.tobytes() if ok else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_frames.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/frames.py hri_monitor/tests/test_frames.py
git commit -m "feat(hri_monitor): frame store with on-demand jpeg encoding"
```

---

### Task 7: FastAPI server — status API and WebSocket telemetry

**Files:**
- Create: `hri_monitor/hub/server.py`
- Test: `hri_monitor/tests/test_server.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_server.py`:

```python
from fastapi.testclient import TestClient

from hub.bus import MessageBus
from hub.server import create_app


class FakeManager:
    def statuses(self):
        return {"shimmer": "connected"}


def make_client():
    bus = MessageBus()
    client = TestClient(create_app(bus, FakeManager()))
    return bus, client


def test_status_endpoint_reports_devices():
    _, client = make_client()
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {"devices": {"shimmer": "connected"}}


def test_ws_sends_hello_then_streams_published_samples():
    bus, client = make_client()
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["devices"] == {"shimmer": "connected"}
        bus.publish("shimmer.gsr", {"value": 4.2})
        update = ws.receive_json()
        assert update["type"] == "update"
        assert update["items"]["shimmer.gsr"]["data"] == {"value": 4.2}
        assert update["devices"] == {"shimmer": "connected"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hub.server'`

- [ ] **Step 3: Implement the server (status + WebSocket only)**

Create `hri_monitor/hub/server.py`:

```python
import asyncio
import threading

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .frames import FrameStore

# Numeric topics forwarded to the dashboard. Frame topics carry numpy arrays
# and are served via MJPEG instead — never JSON.
STREAM_TOPICS = {
    "shimmer.gsr", "shimmer.ppg", "thermal.temps", "rgb.blink",
    "ppg.hr", "ppg.hrv", "model.estimates",
}
WS_FLUSH_SECONDS = 0.1  # dashboard update rate (~10 Hz), spec §4


def create_app(bus, manager, ui_dir=None) -> FastAPI:
    app = FastAPI(title="HRI Monitor")
    frames = FrameStore(bus, {"thermal": "thermal.frame", "rgb": "rgb.frame"})
    app.state.frames = frames

    @app.get("/api/status")
    def status():
        return {"devices": manager.statuses()}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        pending: dict = {}
        lock = threading.Lock()

        def on_message(message):
            if message["topic"] in STREAM_TOPICS:
                with lock:
                    pending[message["topic"]] = {"ts": message["ts"], "data": message["data"]}

        bus.subscribe("*", on_message)
        try:
            await ws.send_json({"type": "hello", "devices": manager.statuses()})
            while True:
                await asyncio.sleep(WS_FLUSH_SECONDS)
                with lock:
                    items = dict(pending)
                    pending.clear()
                if items:
                    await ws.send_json({"type": "update", "items": items,
                                        "devices": manager.statuses()})
        except WebSocketDisconnect:
            pass
        finally:
            bus.unsubscribe("*", on_message)

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_server.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/server.py hri_monitor/tests/test_server.py
git commit -m "feat(hri_monitor): fastapi hub with status api and ws telemetry"
```

---

### Task 8: MJPEG streaming and static UI serving

**Files:**
- Modify: `hri_monitor/hub/server.py`
- Test: `hri_monitor/tests/test_server.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `hri_monitor/tests/test_server.py`:

```python
def test_unknown_stream_feed_returns_404():
    _, client = make_client()
    response = client.get("/stream/nope")
    assert response.status_code == 404


def test_static_ui_served_when_dir_exists(tmp_path):
    (tmp_path / "index.html").write_text("<html><body>hri</body></html>")
    bus = MessageBus()
    client = TestClient(create_app(bus, FakeManager(), ui_dir=tmp_path))
    response = client.get("/")
    assert response.status_code == 200
    assert "hri" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_server.py -v`
Expected: the two new tests FAIL (404 route missing → `/stream/nope` returns 404 from FastAPI anyway — assert on JSON body makes intent explicit; the static test fails with 404). Note: if `test_unknown_stream_feed_returns_404` passes trivially before implementation, that is acceptable — the static test must fail.

- [ ] **Step 3: Implement MJPEG + static mount**

In `hri_monitor/hub/server.py`, extend the imports:

```python
import asyncio
import threading
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .frames import FrameStore
```

Add below `WS_FLUSH_SECONDS`:

```python
MJPEG_FPS = 15
```

Inside `create_app`, after the `ws_endpoint` definition and before `return app`, add:

```python
    @app.get("/stream/{feed}")
    def stream(feed: str):
        if not frames.has(feed):
            return JSONResponse({"error": f"unknown feed '{feed}'"}, status_code=404)

        def gen():
            while True:
                jpg = frames.jpeg(feed)
                if jpg is not None:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
                time.sleep(1.0 / MJPEG_FPS)

        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    if ui_dir and Path(ui_dir).is_dir():
        app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `python -m pytest tests -v`
Expected: all tests pass (config 2, bus 4, sensor base 2, simulators 3, manager 2, frames 1, server 4)

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/server.py hri_monitor/tests/test_server.py
git commit -m "feat(hri_monitor): mjpeg streams and static ui serving"
```

---

### Task 9: Entry point `run.py`

**Files:**
- Create: `hri_monitor/run.py`

- [ ] **Step 1: Implement the entry point**

Create `hri_monitor/run.py`:

```python
#!/usr/bin/env python3
"""HRI Monitor — single entry point. Starts sensors and the web hub, then
opens the dashboard in the default browser."""
import argparse
import logging
import threading
import webbrowser
from pathlib import Path

import uvicorn

from hub.bus import MessageBus
from hub.config import load_config
from hub.sensors.manager import SensorManager
from hub.server import create_app

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="HRI Monitor")
    parser.add_argument("--no-browser", action="store_true", help="do not open the dashboard")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    config = load_config(ROOT / "config.yaml")
    bus = MessageBus()
    manager = SensorManager(bus, config)
    manager.start_all()
    app = create_app(bus, manager, ui_dir=ROOT / "ui_dist")

    host, port = config["server"]["host"], config["server"]["port"]
    if config["server"]["open_browser"] and not args.no_browser:
        threading.Timer(1.5, webbrowser.open, args=[f"http://{host}:{port}"]).start()
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    finally:
        manager.stop_all()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test it manually**

Run:

```bash
cd /home/juanjose-ensta/Documents/HRIServcer/hri_monitor
.venv/bin/python run.py --no-browser &
sleep 4
curl -s http://127.0.0.1:8000/api/status
curl -s -m 2 http://127.0.0.1:8000/stream/thermal | head -c 40 | od -c | head -2
kill %1
```

Expected: status returns `{"devices":{"shimmer":"connected","thermal":"connected","rgb":"connected"}}`; the stream output starts with `--frame` and `Content-Type: image/jpeg`.

- [ ] **Step 3: Commit**

```bash
git add hri_monitor/run.py
git commit -m "feat(hri_monitor): single-command entry point"
```

---

### Task 10: React UI shell with Live page

**Files:**
- Create: `hri_monitor/ui/package.json`, `hri_monitor/ui/tsconfig.json`, `hri_monitor/ui/vite.config.ts`, `hri_monitor/ui/index.html`
- Create: `hri_monitor/ui/src/main.tsx`, `hri_monitor/ui/src/index.css`, `hri_monitor/ui/src/App.tsx`
- Create: `hri_monitor/ui/src/lib/ws.ts`
- Create: `hri_monitor/ui/src/components/SignalChart.tsx`, `hri_monitor/ui/src/components/VideoFeed.tsx`, `hri_monitor/ui/src/components/StatusChip.tsx`
- Create: `hri_monitor/ui/src/pages/Live.tsx`
- Create (built): `hri_monitor/ui_dist/` (vite build output, committed)

- [ ] **Step 1: Write the project files**

Create `hri_monitor/ui/package.json`:

```json
{
  "name": "hri-monitor-ui",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "recharts": "^2.15.1"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.0.0",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "tailwindcss": "^4.0.0",
    "typescript": "^5.5.3",
    "vite": "^5.4.0"
  }
}
```

Create `hri_monitor/ui/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "noEmit": true
  },
  "include": ["src"]
}
```

Create `hri_monitor/ui/vite.config.ts`:

```ts
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { outDir: "../ui_dist", emptyOutDir: true },
  server: {
    proxy: {
      "/ws": { target: "ws://localhost:8000", ws: true },
      "/api": "http://localhost:8000",
      "/stream": "http://localhost:8000",
    },
  },
});
```

Create `hri_monitor/ui/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>HRI Monitor</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `hri_monitor/ui/src/index.css`:

```css
@import "tailwindcss";
```

Create `hri_monitor/ui/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 2: Write the data hook**

Create `hri_monitor/ui/src/lib/ws.ts`:

```ts
import { useEffect, useRef, useState } from "react";

export type Point = { t: number; v: number };
export type LiveState = {
  latest: Record<string, any>;
  series: Record<string, Point[]>;
  devices: Record<string, string>;
  connected: boolean;
};

// Topics drawn as time series, and how to pull a number out of each payload.
const SERIES_EXTRACTORS: Record<string, (d: any) => number> = {
  "shimmer.gsr": (d) => d.value,
  "shimmer.ppg": (d) => d.value,
  "rgb.blink": (d) => d.rate,
  "thermal.temps": (d) => d.forehead,
};
const MAX_POINTS = 300;

export function useLiveData(): LiveState {
  const [state, setState] = useState<LiveState>({
    latest: {},
    series: {},
    devices: {},
    connected: false,
  });
  const retry = useRef(1000);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;

    function connect() {
      ws = new WebSocket(`ws://${location.host}/ws`);
      ws.onopen = () => {
        retry.current = 1000;
        setState((s) => ({ ...s, connected: true }));
      };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "hello") {
          setState((s) => ({ ...s, devices: msg.devices }));
        } else if (msg.type === "update") {
          setState((s) => {
            const latest = { ...s.latest };
            const series = { ...s.series };
            for (const [topic, sample] of Object.entries<any>(msg.items)) {
              latest[topic] = sample.data;
              const extract = SERIES_EXTRACTORS[topic];
              if (extract) {
                const prev = series[topic] ?? [];
                series[topic] = [...prev.slice(-MAX_POINTS + 1), { t: sample.ts, v: extract(sample.data) }];
              }
            }
            return { ...s, latest, series, devices: msg.devices ?? s.devices };
          });
        }
      };
      ws.onclose = () => {
        setState((s) => ({ ...s, connected: false }));
        if (!closed) {
          setTimeout(connect, retry.current);
          retry.current = Math.min(retry.current * 2, 10000);
        }
      };
    }

    connect();
    return () => {
      closed = true;
      ws?.close();
    };
  }, []);

  return state;
}
```

- [ ] **Step 3: Write the components and Live page**

Create `hri_monitor/ui/src/components/SignalChart.tsx`:

```tsx
import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";
import type { Point } from "../lib/ws";

export function SignalChart({ title, unit, color, points, value }: {
  title: string;
  unit: string;
  color: string;
  points: Point[];
  value?: number;
}) {
  return (
    <div className="rounded-xl bg-slate-900 border border-slate-800 p-4">
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="text-sm font-medium text-slate-400">{title}</h3>
        <span className="text-xl font-semibold text-slate-100">
          {value !== undefined ? value.toFixed(2) : "—"}{" "}
          <span className="text-xs text-slate-500">{unit}</span>
        </span>
      </div>
      <div className="h-24">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points}>
            <YAxis domain={["auto", "auto"]} hide />
            <Line type="monotone" dataKey="v" stroke={color} dot={false}
                  isAnimationActive={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
```

Create `hri_monitor/ui/src/components/VideoFeed.tsx`:

```tsx
export function VideoFeed({ title, src }: { title: string; src: string }) {
  return (
    <div className="rounded-xl bg-slate-900 border border-slate-800 p-4">
      <h3 className="text-sm font-medium text-slate-400 mb-2">{title}</h3>
      <img src={src} alt={title}
           className="w-full rounded-lg bg-black aspect-video object-contain" />
    </div>
  );
}
```

Create `hri_monitor/ui/src/components/StatusChip.tsx`:

```tsx
const COLORS: Record<string, string> = {
  connected: "bg-emerald-500/15 text-emerald-400",
  connecting: "bg-amber-500/15 text-amber-400",
  reconnecting: "bg-amber-500/15 text-amber-400",
  disabled: "bg-slate-500/15 text-slate-400",
};

export function StatusChip({ name, status }: { name: string; status: string }) {
  return (
    <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${COLORS[status] ?? COLORS.disabled}`}>
      ● {name} · {status}
    </span>
  );
}
```

Create `hri_monitor/ui/src/pages/Live.tsx`:

```tsx
import { SignalChart } from "../components/SignalChart";
import { StatusChip } from "../components/StatusChip";
import { VideoFeed } from "../components/VideoFeed";
import { useLiveData } from "../lib/ws";

export function Live() {
  const { latest, series, devices, connected } = useLiveData();
  const temps = latest["thermal.temps"];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip name="hub" status={connected ? "connected" : "reconnecting"} />
        {Object.entries(devices).map(([name, status]) => (
          <StatusChip key={name} name={name} status={status} />
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <VideoFeed title="Thermal" src="/stream/thermal" />
        <VideoFeed title="RGB" src="/stream/rgb" />
        <div className="rounded-xl bg-slate-900 border border-slate-800 p-4">
          <h3 className="text-sm font-medium text-slate-400 mb-2">Facial temperatures</h3>
          {temps ? (
            <dl className="grid grid-cols-2 gap-2 text-sm">
              {Object.entries(temps).map(([roi, v]) => (
                <div key={roi} className="flex justify-between rounded bg-slate-800/60 px-2 py-1">
                  <dt className="text-slate-400">{roi.replace("_", " ")}</dt>
                  <dd className="text-slate-100">{(v as number).toFixed(1)}°C</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-slate-500 text-sm">Waiting for thermal data…</p>
          )}
          <p className="mt-3 text-xs text-slate-600">
            Cognitive load & trust estimates arrive in milestone 3.
          </p>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <SignalChart title="GSR" unit="µS" color="#38bdf8"
                     points={series["shimmer.gsr"] ?? []} value={latest["shimmer.gsr"]?.value} />
        <SignalChart title="PPG" unit="mV" color="#fb7185"
                     points={series["shimmer.ppg"] ?? []} value={latest["shimmer.ppg"]?.value} />
        <SignalChart title="Blink rate" unit="blinks/min" color="#a78bfa"
                     points={series["rgb.blink"] ?? []} value={latest["rgb.blink"]?.rate} />
        <SignalChart title="Forehead temp" unit="°C" color="#fbbf24"
                     points={series["thermal.temps"] ?? []} value={temps?.forehead} />
      </div>
    </div>
  );
}
```

Create `hri_monitor/ui/src/App.tsx`:

```tsx
import { useState } from "react";
import { Live } from "./pages/Live";

const PAGES = ["Live", "Devices", "Experiments", "Analysis", "Models", "Settings"] as const;
type Page = (typeof PAGES)[number];

export default function App() {
  const [page, setPage] = useState<Page>("Live");
  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <aside className="w-52 shrink-0 border-r border-slate-800 p-4">
        <h1 className="text-lg font-semibold text-sky-400 mb-6">HRI Monitor</h1>
        <nav className="space-y-1">
          {PAGES.map((p) => (
            <button key={p} onClick={() => setPage(p)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm ${
                page === p ? "bg-sky-500/15 text-sky-300" : "text-slate-400 hover:bg-slate-900"
              }`}>
              {p}
            </button>
          ))}
        </nav>
      </aside>
      <main className="flex-1 p-6">
        {page === "Live" ? <Live /> : (
          <p className="text-slate-500">“{page}” arrives in a later milestone.</p>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Install and build**

Run:

```bash
cd /home/juanjose-ensta/Documents/HRIServcer/hri_monitor/ui
npm install
npm run build
test -f ../ui_dist/index.html && echo BUILD_OK
```

Expected: `BUILD_OK`. (`node_modules/` is gitignored from Task 1.)

- [ ] **Step 5: Verify against the live hub**

Run:

```bash
cd /home/juanjose-ensta/Documents/HRIServcer/hri_monitor
.venv/bin/python run.py --no-browser &
sleep 4
curl -s http://127.0.0.1:8000/ | grep -o "<title>HRI Monitor</title>"
kill %1
```

Expected: `<title>HRI Monitor</title>`. For a visual check, run `python run.py` and confirm the Live page shows both simulated feeds, four moving charts, and green status chips.

- [ ] **Step 6: Commit**

```bash
cd /home/juanjose-ensta/Documents/HRIServcer
git add hri_monitor/ui hri_monitor/ui_dist
git commit -m "feat(hri_monitor): react ui shell with live monitoring page"
```

---

### Task 11: Full regression + end-to-end smoke

**Files:** none (verification only)

- [ ] **Step 1: Run the whole test suite**

Run: `cd /home/juanjose-ensta/Documents/HRIServcer/hri_monitor && .venv/bin/python -m pytest tests -v`
Expected: 18 passed (config 2, bus 4, sensor base 2, simulators 3, manager 2, frames 1, server 4)

- [ ] **Step 2: End-to-end smoke**

Run:

```bash
cd /home/juanjose-ensta/Documents/HRIServcer/hri_monitor
.venv/bin/python run.py --no-browser &
sleep 4
curl -s http://127.0.0.1:8000/api/status
curl -s -m 2 http://127.0.0.1:8000/stream/rgb | head -c 40 | od -c | head -2
curl -s http://127.0.0.1:8000/ | grep -c "HRI Monitor"
kill %1
```

Expected: all three sensors `connected`; MJPEG boundary bytes; count ≥ 1.

- [ ] **Step 3: Commit any stragglers and report**

```bash
git status --short
```

Expected: clean (everything was committed per task). Report milestone 1 complete; milestone 2 (real device drivers + Devices page) is the next plan.
