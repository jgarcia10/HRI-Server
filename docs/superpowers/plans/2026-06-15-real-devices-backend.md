# Milestone 2 Backend — Real Device Drivers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three simulator twins with real hardware drivers (RGB/MediaPipe, thermal/Optris-subprocess, Shimmer/Bluetooth), add a device-control REST API with config persistence and hot-reconfigure, all behind the existing `BaseSensor`/`SensorManager`/bus contract — hardware-free testable.

**Architecture:** Real drivers are `BaseSensor` subclasses emitting the identical bus topics the simulators emit, so Live/FrameStore/WS are untouched. Pure decode/geometry/codec logic lives in module-level functions tested against known inputs; drivers import heavy deps (`cv2`/`mediapipe`/`dlib`/`pyserial`) lazily inside `connect()` so test collection and simulator runs work without them. The thermal driver runs the crash-prone Optris SDK in an isolated subprocess that pipes length-prefixed frames back to a hub-side proxy.

**Tech Stack:** Python 3.10, FastAPI, OpenCV, MediaPipe, dlib, pyserial, stdlib `socket` (AF_BLUETOOTH), `bluetoothctl`, pytest.

**Spec:** `docs/superpowers/specs/2026-06-15-hri-monitor-real-devices.md` (read §3–§7, §9, §10).

**Working dir:** `/home/juanjose-ensta/Documents/HRIServcer/hri_monitor`. Run tests with `.venv/bin/python -m pytest`. `pytest.ini` already sets `pythonpath=.` and disables ROS plugins — don't touch it.

**Topic/payload contract (unchanged from simulators — match exactly):**
`rgb.frame {"frame": ndarray}`, `rgb.blink {"rate": float, "ear": float}`, `thermal.frame {"frame": ndarray}`, `thermal.temps {"forehead","left_cheek","right_cheek","nose": float}`, `shimmer.gsr {"value": float}`, `shimmer.ppg {"value": float}`, new `ppg.hr {"value": float}`, `ppg.hrv {"value": float}`.

---

### Task 1: Dependencies + config keys + save_config

**Files:**
- Modify: `hri_monitor/requirements.txt`
- Modify: `hri_monitor/hub/config.py`
- Test: `hri_monitor/tests/test_config.py` (append)

- [ ] **Step 1: Add real-driver deps to requirements**

Append to `hri_monitor/requirements.txt`:

```
mediapipe>=0.10
dlib>=19.24
pyserial>=3.5
```

Do NOT `pip install` them in this task (heavy; the simulator tests don't need them and CI may lack build tools). Note in your report that hardware deps install is deferred to the manual-smoke task.

- [ ] **Step 2: Write failing tests for new config keys + save_config**

Append to `hri_monitor/tests/test_config.py`:

```python
from hub.config import DEFAULTS, load_config, save_config


def test_defaults_have_real_device_keys():
    s = DEFAULTS["sensors"]
    assert s["rgb"]["index"] == 0 and s["rgb"]["fps"] == 30
    assert s["thermal"]["detector"].endswith(".svm")
    assert s["thermal"]["predictor"].endswith(".dat")
    assert "format_dir" in s["thermal"]
    assert s["shimmer"]["mac"] is None and s["shimmer"]["sampling_rate"] == 200


def test_save_config_roundtrips(tmp_path):
    p = tmp_path / "config.yaml"
    cfg = load_config(p)
    cfg["sensors"]["rgb"]["index"] = 4
    cfg["sensors"]["rgb"]["simulate"] = False
    save_config(p, cfg)
    reloaded = load_config(p)
    assert reloaded["sensors"]["rgb"]["index"] == 4
    assert reloaded["sensors"]["rgb"]["simulate"] is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — `save_config` import error / missing thermal keys.

- [ ] **Step 4: Add keys + save_config**

In `hri_monitor/hub/config.py`, replace the `DEFAULTS` thermal/rgb/shimmer entries so the `sensors` block reads:

```python
    "sensors": {
        "shimmer": {"enabled": True, "simulate": True, "mac": None, "sampling_rate": 200},
        "thermal": {
            "enabled": True, "simulate": True,
            "xml": "15030138.xml",
            "detector": "dlib_files/dlib_face_detector.svm",
            "predictor": "dlib_files/dlib_landmark_predictor.dat",
            "format_dir": "/tmp/optris",
        },
        "rgb": {"enabled": True, "simulate": True, "index": 0, "width": 640, "height": 480, "fps": 30},
    },
```

Append to `hub/config.py`:

```python
def save_config(path: Path | str, cfg: dict) -> None:
    """Persist the full config dict to YAML (generated file; comments not kept)."""
    path = Path(path)
    path.write_text(yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_config.py -v`
Expected: 4 passed (2 original + 2 new).

- [ ] **Step 6: Commit**

```bash
git add hri_monitor/requirements.txt hri_monitor/hub/config.py hri_monitor/tests/test_config.py
git commit -m "feat(hub): real-device config keys, save_config, hardware deps"
```

---

### Task 2: Shimmer GSR/PPG decode functions (pure)

**Files:**
- Create: `hri_monitor/hub/sensors/shimmer_decode.py`
- Test: `hri_monitor/tests/test_shimmer_decode.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_shimmer_decode.py`:

```python
import struct

from hub.sensors.shimmer_decode import clock_wait_for_rate, decode_frame, HeartRate


def make_frame(ppg_raw, gsr_raw, t=1000):
    t0, t1, t2 = t & 0xFF, (t >> 8) & 0xFF, (t >> 16) & 0xFF
    return bytes([0x00, t0, t1, t2]) + struct.pack("HH", ppg_raw, gsr_raw)


def test_decode_frame_gsr_ppg():
    # GSR range bits 0 (Rf=40.2); a mid-scale GSR_raw
    gsr_raw = 2000  # range 0, adc ~2000
    ppg_raw = 2048
    s = decode_frame(make_frame(ppg_raw, gsr_raw))
    assert s["timestamp"] == 1000
    # PPG: 2048 * 3000/4095 ≈ 1500.4
    assert abs(s["ppg"] - 2048 * (3000.0 / 4095.0)) < 0.01
    assert s["gsr"] > 0


def test_decode_frame_each_gsr_range_uses_right_rf():
    rfs = [40.2, 287.0, 1000.0, 3300.0]
    for rng, rf in enumerate(rfs):
        gsr_raw = (rng << 14) | 1000
        s = decode_frame(make_frame(2048, gsr_raw))
        adc = 1000 * (3.0 / 4095.0)
        ohm = rf / ((adc / 0.5) - 1.0)
        assert abs(s["gsr"] - 1_000_000.0 / ohm) < 1.0


def test_clock_wait_for_rate():
    assert clock_wait_for_rate(200) == int((2 << 14) / 200)


def test_heart_rate_from_periodic_peaks():
    hr = HeartRate(fs=200)
    # synth 1.2 Hz sine over 6 s → ~72 bpm
    import math
    bpm = None
    for i in range(200 * 6):
        v = 1500 + 400 * math.sin(2 * math.pi * 1.2 * i / 200.0)
        out = hr.update(v, i / 200.0)
        if out:
            bpm, _hrv = out
    assert bpm is not None and 60 < bpm < 84
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_shimmer_decode.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the decoder**

Create `hri_monitor/hub/sensors/shimmer_decode.py`:

```python
"""Pure Shimmer GSR+/PPG decode + HR/HRV — no hardware, fully unit-tested.
Ported from hri_server.py data_read_loop()."""
import struct

FRAMESIZE = 8
_RF = [40.2, 287.0, 1000.0, 3300.0]  # feedback resistor per GSR range


def clock_wait_for_rate(sampling_rate: int) -> int:
    return int((2 << 14) / sampling_rate)


def decode_frame(data: bytes) -> dict:
    """Decode one 8-byte Shimmer frame → {timestamp, gsr (µS), ppg (mV)}."""
    t0, t1, t2 = data[1], data[2], data[3]
    timestamp = t0 + t1 * 256 + t2 * 65536
    ppg_raw, gsr_raw = struct.unpack("HH", data[4:8])
    rng = (gsr_raw >> 14) & 0x03
    rf = _RF[rng]
    gsr_volts = (gsr_raw & 0x3FFF) * (3.0 / 4095.0)
    gsr_ohm = rf / ((gsr_volts / 0.5) - 1.0)
    gsr_muS = 1_000_000.0 / gsr_ohm
    ppg_mv = ppg_raw * (3000.0 / 4095.0)
    return {"timestamp": timestamp, "gsr": round(gsr_muS, 3), "ppg": round(ppg_mv, 3)}


class HeartRate:
    """Rolling PPG peak detector → (bpm, rmssd_ms). Emits once enough beats seen."""

    def __init__(self, fs: int, window_s: float = 10.0):
        self.fs = fs
        self.window_s = window_s
        self._buf: list[tuple[float, float]] = []  # (t, v)
        self._peaks: list[float] = []  # peak times

    def update(self, ppg: float, t: float):
        self._buf.append((t, ppg))
        self._buf = [(bt, bv) for bt, bv in self._buf if t - bt <= self.window_s]
        if len(self._buf) < 5:
            return None
        # simple local-maximum peak: middle of last 3 samples is a peak above mean
        vals = [v for _, v in self._buf]
        mean = sum(vals) / len(vals)
        a, b, c = self._buf[-3], self._buf[-2], self._buf[-1]
        if b[1] > a[1] and b[1] >= c[1] and b[1] > mean:
            if not self._peaks or b[0] - self._peaks[-1] > 0.33:  # refractory 0.33s (<180bpm)
                self._peaks.append(b[0])
        self._peaks = [pt for pt in self._peaks if t - pt <= self.window_s]
        if len(self._peaks) < 3:
            return None
        intervals = [self._peaks[i + 1] - self._peaks[i] for i in range(len(self._peaks) - 1)]
        mean_ibi = sum(intervals) / len(intervals)
        if mean_ibi <= 0:
            return None
        bpm = 60.0 / mean_ibi
        diffs = [(intervals[i + 1] - intervals[i]) * 1000.0 for i in range(len(intervals) - 1)]
        rmssd = (sum(d * d for d in diffs) / len(diffs)) ** 0.5 if diffs else 0.0
        return round(bpm, 1), round(rmssd, 1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_shimmer_decode.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/sensors/shimmer_decode.py hri_monitor/tests/test_shimmer_decode.py
git commit -m "feat(sensors): pure shimmer gsr/ppg decode + hr/hrv"
```

---

### Task 3: Blink/EAR math (pure)

**Files:**
- Create: `hri_monitor/hub/sensors/blink_math.py`
- Test: `hri_monitor/tests/test_blink_math.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_blink_math.py`:

```python
import numpy as np

from hub.sensors.blink_math import eye_aspect_ratio, BlinkRate


def test_ear_open_vs_closed():
    # open eye: tall; closed eye: flat
    open_eye = np.array([(0, 0), (1, 2), (2, 2), (3, 0), (2, -2), (1, -2)], dtype=float)
    closed_eye = np.array([(0, 0), (1, 0.1), (2, 0.1), (3, 0), (2, -0.1), (1, -0.1)], dtype=float)
    assert eye_aspect_ratio(open_eye) > eye_aspect_ratio(closed_eye)


def test_blink_rate_counts_and_weights():
    br = BlinkRate(ear_threshold=0.25, consecutive=3, window=5.0)
    t = 0.0
    # 3 closed frames then open = 1 blink
    for _ in range(3):
        br.update(0.1, t); t += 0.03
    rate = br.update(0.4, t)  # transition open registers the blink
    assert br.blink_count == 1
    assert rate >= 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_blink_math.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `hri_monitor/hub/sensors/blink_math.py`:

```python
"""Pure EAR + weighted blink-rate logic, ported from hri_server.py blink_loop()."""
import numpy as np

LEFT_EYE_IDX = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_IDX = [362, 385, 387, 263, 373, 380]


def eye_aspect_ratio(eye: np.ndarray) -> float:
    a = np.linalg.norm(eye[1] - eye[5])
    b = np.linalg.norm(eye[2] - eye[4])
    c = np.linalg.norm(eye[0] - eye[3])
    return float((a + b) / (2.0 * c)) if c != 0 else 0.0


class BlinkRate:
    """Weighted blinks/min: 0.1*cumulative + 0.7*sliding(window) + 0.2*instant."""

    def __init__(self, ear_threshold=0.25, consecutive=3, window=5.0):
        self.ear_threshold = ear_threshold
        self.consecutive = consecutive
        self.window = window
        self.blink_count = 0
        self._frames_closed = 0
        self._was_closed = False
        self._start = None
        self._sliding: list[float] = []
        self._last_blink_t = None
        self._instant = 0.0

    def update(self, ear: float, t: float) -> float:
        if self._start is None:
            self._start = t
        if ear < self.ear_threshold:
            self._frames_closed += 1
        else:
            if self._frames_closed >= self.consecutive and not self._was_closed:
                self.blink_count += 1
                self._sliding.append(t)
                if self._last_blink_t is not None:
                    dt = t - self._last_blink_t
                    self._instant = 60.0 / dt if dt > 0 else 0.0
                self._last_blink_t = t
                self._was_closed = True
            self._frames_closed = 0
            self._was_closed = False
        elapsed_min = (t - self._start) / 60.0
        cumulative = self.blink_count / elapsed_min if elapsed_min > 0 else 0.0
        self._sliding = [ts for ts in self._sliding if t - ts <= self.window]
        sliding = len(self._sliding) * (60.0 / self.window)
        return 0.1 * cumulative + 0.7 * sliding + 0.2 * self._instant
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_blink_math.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/sensors/blink_math.py hri_monitor/tests/test_blink_math.py
git commit -m "feat(sensors): pure ear + weighted blink-rate math"
```

---

### Task 4: Thermal framing codec (pure)

**Files:**
- Create: `hri_monitor/hub/sensors/thermal_codec.py`
- Test: `hri_monitor/tests/test_thermal_codec.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_thermal_codec.py`:

```python
import io

import numpy as np

from hub.sensors.thermal_codec import encode_message, read_message


def test_encode_read_roundtrip():
    frame = np.arange(240 * 320 * 3, dtype=np.uint8).reshape((240, 320, 3))
    temps = {"forehead": 34.5, "left_cheek": 33.8, "right_cheek": 33.9, "nose": 32.5}
    blob = encode_message(temps, frame)
    reader = io.BytesIO(blob)
    got_temps, got_frame = read_message(reader)
    assert got_temps == temps
    assert got_frame.shape == frame.shape
    assert np.array_equal(got_frame, frame)


def test_read_message_returns_none_on_eof():
    assert read_message(io.BytesIO(b"")) is None


def test_read_two_messages_in_sequence():
    f = np.zeros((2, 2, 3), dtype=np.uint8)
    stream = io.BytesIO(encode_message({"nose": 30.0}, f) + encode_message({"nose": 31.0}, f))
    m1 = read_message(stream)
    m2 = read_message(stream)
    assert m1[0]["nose"] == 30.0 and m2[0]["nose"] == 31.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_thermal_codec.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the codec**

Create `hri_monitor/hub/sensors/thermal_codec.py`:

```python
"""Length-prefixed frame+temps messages between the thermal worker subprocess
and the hub-side proxy. Format: [4B meta-len][meta JSON][raw uint8 BGR bytes].
meta = {"temps": {...}, "h": int, "w": int}."""
import json
import struct

import numpy as np


def encode_message(temps: dict, frame: np.ndarray) -> bytes:
    h, w = frame.shape[0], frame.shape[1]
    meta = json.dumps({"temps": temps, "h": h, "w": w}).encode("utf-8")
    body = frame.astype(np.uint8).tobytes()
    return struct.pack(">I", len(meta)) + meta + body


def _read_exactly(reader, n: int) -> bytes | None:
    chunks = []
    got = 0
    while got < n:
        chunk = reader.read(n - got)
        if not chunk:
            return None
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


def read_message(reader):
    """Read one message from a binary reader → (temps, frame) or None at EOF."""
    header = _read_exactly(reader, 4)
    if header is None:
        return None
    (meta_len,) = struct.unpack(">I", header)
    meta_bytes = _read_exactly(reader, meta_len)
    if meta_bytes is None:
        return None
    meta = json.loads(meta_bytes.decode("utf-8"))
    h, w = meta["h"], meta["w"]
    body = _read_exactly(reader, h * w * 3)
    if body is None:
        return None
    frame = np.frombuffer(body, dtype=np.uint8).reshape((h, w, 3))
    return meta["temps"], frame
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_thermal_codec.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/sensors/thermal_codec.py hri_monitor/tests/test_thermal_codec.py
git commit -m "feat(sensors): thermal worker framing codec"
```

---

### Task 5: Thermal ROI geometry (pure)

**Files:**
- Create: `hri_monitor/hub/sensors/roi.py`
- Test: `hri_monitor/tests/test_roi.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_roi.py`:

```python
from hub.sensors.roi import RegionsOfInterest, scale_roi_to_thermal


def test_regions_selects_named_boxes():
    xs = list(range(68))
    ys = list(range(68))
    roi = RegionsOfInterest(xs, ys)
    sel = roi.get(["forehead", "left_cheek", "right_cheek", "nose"])
    assert set(sel) == {"forehead", "left_cheek", "right_cheek", "nose"}
    for box in sel.values():
        assert len(box) == 4


def test_scale_roi_clamps_into_thermal_bounds():
    # palette 320x240 → thermal 160x120 (scale 0.5)
    box = scale_roi_to_thermal((10, 20, 50, 60), sx=0.5, sy=0.5, tw=160, th=120)
    assert box == (5, 10, 25, 30)
    # out-of-range clamps
    big = scale_roi_to_thermal((0, 0, 1000, 1000), sx=0.5, sy=0.5, tw=160, th=120)
    assert big[2] <= 160 and big[3] <= 120
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_roi.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement** (port `RegionsOfInterest` from `hri_server.py`, add scaling helper)

Create `hri_monitor/hub/sensors/roi.py`:

```python
"""Facial ROI boxes from dlib 68-landmarks + scaling to the thermal array.
Ported from hri_server.py RegionsOfInterest."""


class RegionsOfInterest:
    def __init__(self, coords_x, coords_y):
        self.x = coords_x
        self.y = coords_y
        self.eyes_dist = self.x[45] - self.x[36]
        self.regions = {
            "forehead": self._forehead(),
            "left_cheek": self._left_cheek(),
            "right_cheek": self._right_cheek(),
            "nose": self._nose(),
        }

    def _forehead(self):
        interm = self.x[23] - self.x[20]
        return [self.x[21], self.y[20] - interm / 2, self.x[22], self.y[23] - interm / 4]

    def _left_cheek(self):
        return [self.x[4], self.y[14], self.x[6], self.y[13]]

    def _right_cheek(self):
        return [self.x[10], self.y[14], self.x[12], self.y[13]]

    def _nose(self):
        return [self.x[32], self.y[29], self.x[34], self.y[30]]

    def get(self, names):
        return {n: self.regions[n] for n in names if n in self.regions}


def scale_roi_to_thermal(box, sx, sy, tw, th):
    """Scale a palette-space (x0,y0,x1,y1) box into thermal pixel coords, clamped."""
    x0, y0, x1, y1 = box
    tx0 = max(0, min(int(x0 * sx), tw - 1))
    ty0 = max(0, min(int(y0 * sy), th - 1))
    tx1 = max(0, min(int(x1 * sx), tw))
    ty1 = max(0, min(int(y1 * sy), th))
    return tx0, ty0, tx1, ty1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_roi.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/sensors/roi.py hri_monitor/tests/test_roi.py
git commit -m "feat(sensors): facial roi geometry + thermal scaling"
```

---

### Task 6: Camera + Bluetooth + serial helpers (parsing tested)

**Files:**
- Create: `hri_monitor/hub/cameras.py`
- Create: `hri_monitor/hub/bluetooth.py`
- Test: `hri_monitor/tests/test_cameras.py`
- Test: `hri_monitor/tests/test_bluetooth.py`

- [ ] **Step 1: Write the failing tests**

Create `hri_monitor/tests/test_cameras.py`:

```python
from hub.cameras import list_cameras_from_sysfs


def test_list_cameras_reads_names(tmp_path):
    # fake /sys/class/video4linux tree
    for idx, name in [(0, "Integrated Cam"), (2, "USB Webcam")]:
        d = tmp_path / f"video{idx}"
        d.mkdir()
        (d / "name").write_text(name + "\n")
    cams = list_cameras_from_sysfs(str(tmp_path))
    assert {"index": 0, "path": "/dev/video0", "name": "Integrated Cam"} in cams
    assert {"index": 2, "path": "/dev/video2", "name": "USB Webcam"} in cams
    assert cams == sorted(cams, key=lambda c: c["index"])
```

Create `hri_monitor/tests/test_bluetooth.py`:

```python
from hub.bluetooth import parse_devices


def test_parse_bluetoothctl_devices():
    text = (
        "Device 00:06:66:8C:4A:2C Shimmer3-4A2C\n"
        "Device A8:51:AB:CD:EF:01 JBL Flip\n"
        "garbage line\n"
    )
    paired = {"00:06:66:8C:4A:2C"}
    devs = parse_devices(text, paired)
    assert {"mac": "00:06:66:8C:4A:2C", "name": "Shimmer3-4A2C", "paired": True} in devs
    assert {"mac": "A8:51:AB:CD:EF:01", "name": "JBL Flip", "paired": False} in devs
    assert len(devs) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_cameras.py tests/test_bluetooth.py -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement cameras.py**

Create `hri_monitor/hub/cameras.py`:

```python
"""V4L2 camera enumeration via sysfs (dependency-free)."""
import os
import re

_SYSFS = "/sys/class/video4linux"
_VIDEO_RE = re.compile(r"^video(\d+)$")


def list_cameras_from_sysfs(root: str = _SYSFS) -> list[dict]:
    cams = []
    if not os.path.isdir(root):
        return cams
    for entry in os.listdir(root):
        m = _VIDEO_RE.match(entry)
        if not m:
            continue
        idx = int(m.group(1))
        name_path = os.path.join(root, entry, "name")
        try:
            name = open(name_path).read().strip()
        except OSError:
            name = entry
        cams.append({"index": idx, "path": f"/dev/video{idx}", "name": name})
    return sorted(cams, key=lambda c: c["index"])


def list_cameras() -> list[dict]:
    return list_cameras_from_sysfs()
```

- [ ] **Step 4: Implement bluetooth.py**

Create `hri_monitor/hub/bluetooth.py`:

```python
"""bluetoothctl wrapper for scan/pair + serial-port listing. Subprocess calls
are timed out; output parsing is pure and unit-tested."""
import glob
import re
import subprocess

_DEV_RE = re.compile(r"^Device ([0-9A-F:]{17}) (.+)$")


def parse_devices(text: str, paired_macs: set) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = _DEV_RE.match(line.strip())
        if not m:
            continue
        mac, name = m.group(1), m.group(2).strip()
        out.append({"mac": mac, "name": name, "paired": mac in paired_macs})
    return out


def _run(args, timeout):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def _paired_macs() -> set:
    try:
        r = _run(["bluetoothctl", "paired-devices"], 5)
        return {m.group(1) for line in r.stdout.splitlines()
                if (m := _DEV_RE.match(line.strip()))}
    except Exception:
        return set()


def scan(seconds: int = 8) -> list[dict]:
    try:
        subprocess.run(["bluetoothctl", "--timeout", str(seconds), "scan", "on"],
                       capture_output=True, text=True, timeout=seconds + 5)
        r = _run(["bluetoothctl", "devices"], 5)
        return parse_devices(r.stdout, _paired_macs())
    except Exception as e:
        return []


def pair(mac: str, pin: str = "1234") -> dict:
    try:
        p = _run(["bluetoothctl", "pair", mac], 25)
        ok = "Paired: yes" in p.stdout or "successful" in p.stdout.lower()
        if ok:
            _run(["bluetoothctl", "trust", mac], 5)
        return {"ok": ok, "reason": p.stdout.strip()[-200:] or p.stderr.strip()[-200:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "pair timed out (confirm PIN on device)"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def list_serial_ports() -> list[str]:
    return sorted(glob.glob("/dev/rfcomm*") + glob.glob("/dev/ttyUSB*"))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_cameras.py tests/test_bluetooth.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add hri_monitor/hub/cameras.py hri_monitor/hub/bluetooth.py hri_monitor/tests/test_cameras.py hri_monitor/tests/test_bluetooth.py
git commit -m "feat(hub): camera enumeration + bluetooth helper"
```

---

### Task 7: RealRGB driver

**Files:**
- Create: `hri_monitor/hub/sensors/rgb.py`
- Test: `hri_monitor/tests/test_rgb_driver.py`

- [ ] **Step 1: Write the failing tests** (no hardware: test lazy-import guard + construction)

Create `hri_monitor/tests/test_rgb_driver.py`:

```python
from hub.bus import MessageBus
from hub.sensors.rgb import RealRGB


def test_realrgb_is_basesensor_with_config():
    bus = MessageBus()
    s = RealRGB(bus, index=2, width=640, height=480, fps=30)
    assert s.name == "rgb"
    assert s.index == 2 and s.width == 640 and s.fps == 30
    assert s.status == "disabled"


def test_realrgb_connect_raises_clean_when_cv2_missing(monkeypatch):
    # Simulate a machine without a usable camera/deps: connect must raise, not crash import.
    bus = MessageBus()
    s = RealRGB(bus, index=999, width=640, height=480, fps=30)
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "cv2":
            raise ImportError("no cv2")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    try:
        s.connect()
        raised = False
    except Exception:
        raised = True
    assert raised
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_rgb_driver.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement RealRGB**

Create `hri_monitor/hub/sensors/rgb.py`:

```python
"""Real USB RGB camera → MediaPipe blink/EAR. Heavy deps imported lazily in
connect() so the hub starts without cv2/mediapipe present."""
import time

import numpy as np

from .base import BaseSensor
from .blink_math import LEFT_EYE_IDX, RIGHT_EYE_IDX, BlinkRate, eye_aspect_ratio


class RealRGB(BaseSensor):
    name = "rgb"

    def __init__(self, bus, index=0, width=640, height=480, fps=30):
        super().__init__(bus)
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self._cap = None
        self._mesh = None
        self._blink = None

    def connect(self):
        import cv2
        import mediapipe as mp

        self._cv2 = cv2
        cap = cv2.VideoCapture(self.index, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f"cannot open camera /dev/video{self.index}")
        self._cap = cap
        self._mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1, refine_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)
        self._blink = BlinkRate()

    def read(self):
        cv2 = self._cv2
        ok, frame = self._cap.read()
        if not ok:
            raise RuntimeError("camera read failed")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._mesh.process(rgb)
        t = time.time()
        ear = 0.0
        if results.multi_face_landmarks:
            h, w, _ = frame.shape
            lm = results.multi_face_landmarks[0]

            def pts(idx):
                return np.array([(lm.landmark[i].x * w, lm.landmark[i].y * h) for i in idx])

            left, right = pts(LEFT_EYE_IDX), pts(RIGHT_EYE_IDX)
            ear = (eye_aspect_ratio(left) + eye_aspect_ratio(right)) / 2.0
            for p in np.vstack([left, right]).astype(int):
                cv2.circle(frame, tuple(p), 2, (0, 255, 0), -1)
            cv2.putText(frame, f"EAR: {ear:.2f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        rate = self._blink.update(ear, t)
        cv2.putText(frame, f"Blink: {rate:.1f}/min", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        self.emit("rgb.frame", {"frame": frame})
        self.emit("rgb.blink", {"rate": round(max(rate, 0.0), 2), "ear": round(ear, 3)})
        time.sleep(0.01)

    def disconnect(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self._mesh is not None:
            self._mesh.close()
            self._mesh = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_rgb_driver.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/sensors/rgb.py hri_monitor/tests/test_rgb_driver.py
git commit -m "feat(sensors): real rgb camera driver (mediapipe blink)"
```

---

### Task 8: RealShimmer driver

**Files:**
- Create: `hri_monitor/hub/sensors/shimmer.py`
- Test: `hri_monitor/tests/test_shimmer_driver.py`

- [ ] **Step 1: Write the failing tests** (no hardware: construction + read decodes from a fake socket)

Create `hri_monitor/tests/test_shimmer_driver.py`:

```python
import struct

from hub.bus import MessageBus
from hub.sensors.shimmer import RealShimmer


class FakeSock:
    def __init__(self, payload):
        self._buf = payload
    def recv(self, n):
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk
    def settimeout(self, t): pass
    def close(self): pass


def test_realshimmer_construction():
    s = RealShimmer(MessageBus(), mac="00:06:66:8C:4A:2C", sampling_rate=200)
    assert s.name == "shimmer" and s.mac.endswith("4A:2C") and s.sampling_rate == 200
    assert s.status == "disabled"


def test_realshimmer_read_emits_gsr_ppg():
    bus = MessageBus()
    got = {"gsr": [], "ppg": []}
    bus.subscribe("shimmer.gsr", lambda m: got["gsr"].append(m["data"]["value"]))
    bus.subscribe("shimmer.ppg", lambda m: got["ppg"].append(m["data"]["value"]))
    s = RealShimmer(bus, mac="x", sampling_rate=200)
    frame = bytes([0x00, 0xE8, 0x03, 0x00]) + struct.pack("HH", 2048, 2000)
    s._sock = FakeSock(frame)  # inject; bypass connect()
    s.read()
    assert len(got["ppg"]) == 1 and got["ppg"][0] > 0
    assert len(got["gsr"]) == 1 and got["gsr"][0] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_shimmer_driver.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement RealShimmer**

Create `hri_monitor/hub/sensors/shimmer.py`:

```python
"""Real Shimmer GSR+ over a Bluetooth RFCOMM socket (stdlib). Config handshake
and decode ported from hri_server.py shimmer_main/data_read_loop."""
import socket
import struct
import time

from .base import BaseSensor
from .shimmer_decode import FRAMESIZE, HeartRate, clock_wait_for_rate, decode_frame

ACK = struct.pack("B", 0xFF)


class RealShimmer(BaseSensor):
    name = "shimmer"
    stale_after = 3.0

    def __init__(self, bus, mac=None, sampling_rate=200, connect_timeout=10.0):
        super().__init__(bus)
        self.mac = mac
        self.sampling_rate = sampling_rate
        self.connect_timeout = connect_timeout
        self._sock = None
        self._hr = HeartRate(fs=sampling_rate)
        self._buf = b""

    def _wait_ack(self):
        while True:
            b = self._sock.recv(1)
            if not b:
                raise RuntimeError("socket closed during handshake")
            if b == ACK:
                return

    def connect(self):
        if not self.mac:
            raise RuntimeError("no Bluetooth MAC configured")
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        s.settimeout(self.connect_timeout)
        s.connect((self.mac, 1))  # RFCOMM channel 1 (SPP)
        self._sock = s
        s.sendall(struct.pack("BBBB", 0x08, 0x04, 0x01, 0x00)); self._wait_ack()
        s.sendall(struct.pack("BB", 0x5E, 0x01)); self._wait_ack()
        s.sendall(struct.pack("<BH", 0x05, clock_wait_for_rate(self.sampling_rate))); self._wait_ack()
        s.sendall(struct.pack("B", 0x07)); self._wait_ack()
        s.settimeout(2.0)  # read timeout so a dead sensor trips the watchdog
        self._buf = b""

    def read(self):
        while len(self._buf) < FRAMESIZE:
            chunk = self._sock.recv(FRAMESIZE - len(self._buf))
            if not chunk:
                raise RuntimeError("shimmer socket closed")
            self._buf += chunk
        frame, self._buf = self._buf[:FRAMESIZE], self._buf[FRAMESIZE:]
        s = decode_frame(frame)
        t = time.time()
        self.emit("shimmer.gsr", {"value": s["gsr"]})
        self.emit("shimmer.ppg", {"value": s["ppg"]})
        hr = self._hr.update(s["ppg"], t)
        if hr:
            bpm, hrv = hr
            self.emit("ppg.hr", {"value": bpm})
            self.emit("ppg.hrv", {"value": hrv})

    def disconnect(self):
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_shimmer_driver.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/sensors/shimmer.py hri_monitor/tests/test_shimmer_driver.py
git commit -m "feat(sensors): real shimmer rfcomm driver"
```

---

### Task 9: Thermal worker + proxy

**Files:**
- Create: `hri_monitor/hub/sensors/thermal_worker.py`
- Create: `hri_monitor/hub/sensors/thermal.py`
- Test: `hri_monitor/tests/test_thermal_driver.py`

- [ ] **Step 1: Write the failing tests** (no hardware: proxy reads from a fake worker stdout; worker import guarded)

Create `hri_monitor/tests/test_thermal_driver.py`:

```python
import io

import numpy as np

from hub.bus import MessageBus
from hub.sensors.thermal import ThermalProcess
from hub.sensors.thermal_codec import encode_message


def test_thermalprocess_construction():
    s = ThermalProcess(MessageBus(), xml="15030138.xml",
                       detector="d.svm", predictor="p.dat", format_dir="/tmp/x")
    assert s.name == "thermal" and s.xml == "15030138.xml"
    assert s.status == "disabled"


def test_thermalprocess_read_emits_from_pipe():
    bus = MessageBus()
    temps_got, frame_got = [], []
    bus.subscribe("thermal.temps", lambda m: temps_got.append(m["data"]))
    bus.subscribe("thermal.frame", lambda m: frame_got.append(m["data"]["frame"]))
    s = ThermalProcess(bus, xml="x", detector="d", predictor="p", format_dir="/tmp")
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    s._stdout = io.BytesIO(encode_message({"nose": 31.2}, frame))  # inject fake worker pipe
    s.read()
    assert temps_got == [{"nose": 31.2}]
    assert frame_got[0].shape == (4, 4, 3)


def test_thermalprocess_read_raises_on_worker_death():
    s = ThermalProcess(MessageBus(), xml="x", detector="d", predictor="p", format_dir="/tmp")
    s._stdout = io.BytesIO(b"")  # EOF = worker died
    try:
        s.read()
        raised = False
    except Exception:
        raised = True
    assert raised
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_thermal_driver.py -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement the proxy** `hri_monitor/hub/sensors/thermal.py`

```python
"""Hub-side proxy for the isolated Optris thermal worker subprocess. The proxy
is a BaseSensor; connect() spawns the worker, read() emits framed messages."""
import os
import subprocess
import sys

from .base import BaseSensor
from .thermal_codec import read_message


class ThermalProcess(BaseSensor):
    name = "thermal"
    stale_after = 8.0

    def __init__(self, bus, xml=None, detector=None, predictor=None, format_dir="/tmp/optris"):
        super().__init__(bus)
        self.xml = xml
        self.detector = detector
        self.predictor = predictor
        self.format_dir = format_dir
        self._proc = None
        self._stdout = None

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
        # First message proves the SDK initialized; if the worker dies, surface stderr.
        first = read_message(self._stdout)
        if first is None:
            err = self._proc.stderr.read().decode("utf-8", "replace")[-300:] if self._proc.stderr else ""
            raise RuntimeError(f"thermal worker failed to start: {err}")
        self._emit_message(first)

    def read(self):
        msg = read_message(self._stdout)
        if msg is None:
            raise RuntimeError("thermal worker died (pipe EOF)")
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
```

- [ ] **Step 4: Implement the worker** `hri_monitor/hub/sensors/thermal_worker.py`

```python
"""Standalone Optris-SDK + dlib subprocess. Writes length-prefixed frame+temps
messages to stdout. Ported from hri_server.py capture_loop(). Runs in its own
process so an SDK segfault cannot crash the hub."""
import argparse
import ctypes as ct
import sys
import time

import numpy as np

from hub.sensors.roi import RegionsOfInterest, scale_roi_to_thermal
from hub.sensors.thermal_codec import encode_message


class EvoIRFrameMetadata(ct.Structure):
    _fields_ = [
        ("counter", ct.c_uint), ("counterHW", ct.c_uint),
        ("timestamp", ct.c_longlong), ("timestampMedia", ct.c_longlong),
        ("flagState", ct.c_int), ("tempChip", ct.c_float),
        ("tempFlag", ct.c_float), ("tempBox", ct.c_float),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", required=True)
    ap.add_argument("--detector", required=True)
    ap.add_argument("--predictor", required=True)
    ap.add_argument("--format-dir", required=True)
    args = ap.parse_args()

    import cv2
    import dlib

    libir = ct.cdll.LoadLibrary(ct.util.find_library("irdirectsdk"))
    pw, ph, tw, th = ct.c_int(), ct.c_int(), ct.c_int(), ct.c_int()
    meta = EvoIRFrameMetadata()
    if libir.evo_irimager_usb_init(args.xml.encode(), args.format_dir.encode(), b"log") != 0:
        print("evo_irimager_usb_init failed", file=sys.stderr); sys.exit(2)
    libir.evo_irimager_get_thermal_image_size(ct.byref(tw), ct.byref(th))
    libir.evo_irimager_get_palette_image_size(ct.byref(pw), ct.byref(ph))
    np_thermal = np.zeros([tw.value * th.value], dtype=np.uint16)
    np_img = np.zeros([pw.value * ph.value * 3], dtype=np.uint8)
    p_th = np_thermal.ctypes.data_as(ct.POINTER(ct.c_ushort))
    p_im = np_img.ctypes.data_as(ct.POINTER(ct.c_ubyte))

    detector = dlib.simple_object_detector(args.detector)
    predictor = dlib.shape_predictor(args.predictor)
    last_detect = 0.0
    rect = None
    last_valid = {}
    out = sys.stdout.buffer

    while True:
        if libir.evo_irimager_get_thermal_palette_image_metadata(
                tw, th, p_th, pw, ph, p_im, ct.byref(meta)) != 0:
            continue
        thermal = np_thermal.reshape((th.value, tw.value)).astype(np.float32)
        tmap = thermal / 10.0 - 100.0
        palette = np_img.reshape((ph.value, pw.value, 3))
        display = palette[:, :, ::-1].copy()  # BGR for output + dlib
        now = time.time()
        if rect is None or now - last_detect > 5.0:
            dets = detector(cv2.cvtColor(display, cv2.COLOR_BGR2GRAY))
            rect = dets[0] if dets else None
            if rect is not None:
                last_detect = now
        temps = {}
        if rect is not None:
            shape = predictor(display, rect)
            xs = [p.x for p in shape.parts()]
            ys = [p.y for p in shape.parts()]
            roi = RegionsOfInterest(xs, ys)
            sx, sy = tw.value / pw.value, th.value / ph.value
            for name, box in roi.get(["forehead", "left_cheek", "right_cheek", "nose"]).items():
                x0, y0, x1, y1 = map(int, box)
                cv2.rectangle(display, (x0, y0), (x1, y1), (0, 255, 0), 2)
                tx0, ty0, tx1, ty1 = scale_roi_to_thermal((x0, y0, x1, y1), sx, sy, tw.value, th.value)
                if tx1 > tx0 and ty1 > ty0:
                    temps[name] = round(float(np.mean(tmap[ty0:ty1, tx0:tx1])), 2)
        if temps and all(v is not None for v in temps.values()):
            last_valid = temps.copy()
        elif last_valid:
            temps = last_valid.copy()
        out.write(encode_message(temps, display))
        out.flush()
        time.sleep(0.03)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_thermal_driver.py -v`
Expected: 3 passed. (The worker is not imported by the tests — only the proxy and codec are — so dlib/optris absence is fine.)

- [ ] **Step 6: Commit**

```bash
git add hri_monitor/hub/sensors/thermal.py hri_monitor/hub/sensors/thermal_worker.py hri_monitor/tests/test_thermal_driver.py
git commit -m "feat(sensors): isolated optris thermal worker + hub proxy"
```

---

### Task 10: SensorManager real-vs-sim factory + reconfigure

**Files:**
- Modify: `hri_monitor/hub/sensors/manager.py`
- Test: `hri_monitor/tests/test_manager.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `hri_monitor/tests/test_manager.py`:

```python
import copy as _copy

from hub.sensors.rgb import RealRGB
from hub.sensors.simulators import SimulatedRGB


def test_build_picks_real_or_sim_by_flag():
    cfg = _copy.deepcopy(DEFAULTS)
    cfg["sensors"]["rgb"]["simulate"] = True
    m = SensorManager(MessageBus(), cfg)
    assert isinstance(m.sensors["rgb"], SimulatedRGB)

    cfg2 = _copy.deepcopy(DEFAULTS)
    cfg2["sensors"]["rgb"]["simulate"] = False
    cfg2["sensors"]["rgb"]["index"] = 3
    m2 = SensorManager(MessageBus(), cfg2)
    assert isinstance(m2.sensors["rgb"], RealRGB)
    assert m2.sensors["rgb"].index == 3


def test_reconfigure_swaps_sensor_live(monkeypatch):
    # Stub start() so the rebuilt RealRGB never spawns a thread that opens a real
    # camera — keeps this test hardware-free even though /dev/videoN may exist.
    monkeypatch.setattr("hub.sensors.rgb.RealRGB.start", lambda self: None)
    cfg = _copy.deepcopy(DEFAULTS)  # rgb simulate True
    m = SensorManager(MessageBus(), cfg)
    assert isinstance(m.sensors["rgb"], SimulatedRGB)
    m.reconfigure("rgb", {"simulate": False, "index": 5})
    assert isinstance(m.sensors["rgb"], RealRGB)
    assert m.sensors["rgb"].index == 5
    assert m.config["sensors"]["rgb"]["index"] == 5
```

(`DEFAULTS`, `SensorManager`, `MessageBus` are already imported at the top of the existing `test_manager.py`.)

Note: `test_build_picks_real_or_sim_by_flag` is safe without a stub — `SensorManager.__init__` only *builds* sensors (constructs `RealRGB(...)`, which just stores params); it never calls `start()`, so no camera is opened.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_manager.py -v`
Expected: FAIL — `reconfigure` missing / still builds simulator.

- [ ] **Step 3: Rewrite `hri_monitor/hub/sensors/manager.py`**

```python
import threading

from .rgb import RealRGB
from .shimmer import RealShimmer
from .simulators import SimulatedRGB, SimulatedShimmer, SimulatedThermal
from .thermal import ThermalProcess


class SensorManager:
    """Builds sensors from config (real or simulator per the `simulate` flag) and
    owns their lifecycle, including live single-sensor reconfigure."""

    def __init__(self, bus, config: dict):
        self.bus = bus
        self.config = config
        self._lock = threading.Lock()
        self.sensors = {}
        for name in ("shimmer", "thermal", "rgb"):
            if config["sensors"][name]["enabled"]:
                self.sensors[name] = self._build(name, config["sensors"][name])

    def _build(self, name, c):
        if name == "rgb":
            return (SimulatedRGB(self.bus) if c["simulate"]
                    else RealRGB(self.bus, index=c["index"], width=c["width"],
                                 height=c["height"], fps=c["fps"]))
        if name == "shimmer":
            return (SimulatedShimmer(self.bus) if c["simulate"]
                    else RealShimmer(self.bus, mac=c["mac"], sampling_rate=c["sampling_rate"]))
        if name == "thermal":
            return (SimulatedThermal(self.bus) if c["simulate"]
                    else ThermalProcess(self.bus, xml=c["xml"], detector=c["detector"],
                                        predictor=c["predictor"], format_dir=c["format_dir"]))
        raise ValueError(f"unknown sensor {name}")

    def start_all(self):
        for s in self.sensors.values():
            s.start()

    def stop_all(self):
        for s in self.sensors.values():
            s.stop()

    def statuses(self):
        with self._lock:
            return {name: s.status for name, s in self.sensors.items()}

    def reconfigure(self, name: str, updates: dict):
        """Merge `updates` into config[name], persist nothing here (caller saves),
        rebuild and restart just that sensor."""
        with self._lock:
            if name not in self.config["sensors"]:
                raise KeyError(name)
            self.config["sensors"][name].update(updates)
            old = self.sensors.get(name)
            if old is not None:
                old.stop()
            sensor = self._build(name, self.config["sensors"][name])
            self.sensors[name] = sensor
        sensor.start()

    def restart(self, name: str):
        with self._lock:
            s = self.sensors.get(name)
        if s is not None:
            s.stop()
            s.start()

    def disconnect(self, name: str):
        with self._lock:
            s = self.sensors.get(name)
        if s is not None:
            s.stop()

    def connect(self, name: str):
        with self._lock:
            s = self.sensors.get(name)
        if s is not None:
            s.start()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_manager.py -v`
Expected: all pass (2 original + 2 new). Then run the full suite: `.venv/bin/python -m pytest tests -q` — all green (no hardware opened; reconfigure builds but does not start in the type-assert tests... note: `reconfigure` DOES call `sensor.start()`. RealRGB.start() spawns a thread that calls connect() which lazy-imports cv2 and tries to open /dev/video5 — it will fail and the watchdog will retry. That's fine for the test: the test asserts the object type immediately after reconfigure returns, before any retry matters, and stop_all isn't called. To keep the suite clean, the test does NOT call start_all and the manager's reconfigure starts only the rebuilt sensor. If the dangling RealRGB thread logs reconnecting warnings, that's acceptable; to avoid a leaked thread, the test ends and the daemon thread dies with the process.)

If the leaked daemon thread causes flakiness, adjust `test_reconfigure_swaps_sensor_live` to call `m.sensors["rgb"].stop()` at the end. Include that stop() call to be safe.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/sensors/manager.py hri_monitor/tests/test_manager.py
git commit -m "feat(sensors): manager real/sim factory + live reconfigure"
```

---

### Task 11: Device-control + Bluetooth REST API

**Files:**
- Modify: `hri_monitor/hub/server.py`
- Test: `hri_monitor/tests/test_server.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `hri_monitor/tests/test_server.py`:

```python
def test_devices_endpoint_lists_config_and_options(monkeypatch):
    import hub.server as srv
    monkeypatch.setattr(srv.cameras, "list_cameras", lambda: [{"index": 0, "path": "/dev/video0", "name": "Cam"}])

    class M:
        config = {"sensors": {"rgb": {"simulate": True, "index": 0, "width": 640, "height": 480, "fps": 30}}}
        def statuses(self): return {"rgb": "connected"}
    from hub.bus import MessageBus
    from fastapi.testclient import TestClient
    client = TestClient(srv.create_app(MessageBus(), M()))
    r = client.get("/api/devices")
    assert r.status_code == 200
    body = r.json()
    assert body["devices"]["rgb"]["status"] == "connected"
    assert body["devices"]["rgb"]["config"]["index"] == 0
    assert body["options"]["cameras"][0]["name"] == "Cam"


def test_device_config_post_persists_and_reconfigures(tmp_path, monkeypatch):
    import hub.server as srv
    calls = {}

    class M:
        config = {"sensors": {"rgb": {"simulate": True, "index": 0, "width": 640, "height": 480, "fps": 30}}}
        def statuses(self): return {"rgb": "connected"}
        def reconfigure(self, name, updates): calls["reconf"] = (name, updates)
    saved = {}
    monkeypatch.setattr(srv, "save_config", lambda p, c: saved.setdefault("c", c))
    from hub.bus import MessageBus
    from fastapi.testclient import TestClient
    client = TestClient(srv.create_app(MessageBus(), M(), config_path=tmp_path / "config.yaml"))
    r = client.post("/api/devices/rgb/config", json={"index": 7, "simulate": False})
    assert r.status_code == 200
    assert calls["reconf"][0] == "rgb" and calls["reconf"][1]["index"] == 7
    assert "c" in saved


def test_bluetooth_scan_endpoint(monkeypatch):
    import hub.server as srv
    monkeypatch.setattr(srv.bluetooth, "scan", lambda seconds=8: [{"mac": "AA", "name": "Shimmer3", "paired": False}])
    from hub.bus import MessageBus
    from fastapi.testclient import TestClient
    client = TestClient(srv.create_app(MessageBus(), FakeManager()))
    r = client.post("/api/bluetooth/scan", json={"seconds": 2})
    assert r.status_code == 200 and r.json()["devices"][0]["name"] == "Shimmer3"
```

(`FakeManager` already exists at the top of `test_server.py` from milestone 1; extend it with `config = {"sensors": {}}` if the bluetooth test needs it — add that attribute to the existing `FakeManager`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_server.py -v`
Expected: FAIL — new endpoints missing.

- [ ] **Step 3: Extend `create_app` in `hri_monitor/hub/server.py`**

Add imports at the top (with the existing imports):

```python
from pydantic import BaseModel

from . import bluetooth, cameras
from .config import save_config
```

Change the signature and add endpoints. Replace `def create_app(bus, manager, ui_dir=None) -> FastAPI:` with:

```python
def create_app(bus, manager, ui_dir=None, config_path="config.yaml") -> FastAPI:
```

Inside `create_app`, after the existing `/api/status` route, add:

```python
    SAMPLING_RATES = [128, 200, 256, 512]

    @app.get("/api/devices")
    def devices():
        cfg = getattr(manager, "config", {}).get("sensors", {})
        st = manager.statuses()
        out = {}
        for name, c in cfg.items():
            out[name] = {"config": c, "status": st.get(name, "disabled")}
        return {
            "devices": out,
            "options": {
                "cameras": cameras.list_cameras(),
                "sampling_rates": SAMPLING_RATES,
                "serial_ports": bluetooth.list_serial_ports(),
            },
        }

    class DeviceConfig(BaseModel):
        simulate: bool | None = None
        index: int | None = None
        width: int | None = None
        height: int | None = None
        fps: int | None = None
        xml: str | None = None
        mac: str | None = None
        sampling_rate: int | None = None

    @app.post("/api/devices/{name}/config")
    def set_device_config(name: str, body: DeviceConfig):
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        manager.reconfigure(name, updates)
        save_config(config_path, manager.config)
        return {"ok": True, "config": manager.config["sensors"].get(name)}

    @app.post("/api/devices/{name}/{action}")
    def device_action(name: str, action: str):
        if action == "restart":
            manager.restart(name)
        elif action == "connect":
            manager.connect(name)
        elif action == "disconnect":
            manager.disconnect(name)
        else:
            return JSONResponse({"error": f"unknown action '{action}'"}, status_code=400)
        return {"ok": True}

    class BtScan(BaseModel):
        seconds: int = 8

    @app.post("/api/bluetooth/scan")
    def bt_scan(body: BtScan):
        return {"devices": bluetooth.scan(seconds=body.seconds)}

    class BtPair(BaseModel):
        mac: str
        pin: str = "1234"

    @app.post("/api/bluetooth/pair")
    def bt_pair(body: BtPair):
        return bluetooth.pair(body.mac, body.pin)
```

Note: register these BEFORE the `/stream/{feed}` route and the static mount so the static catch-all can't shadow them — place them right after `/api/status`. The static mount at `app.mount("/", ...)` already comes last in the function, so this ordering holds.

Also update `run.py` to pass `config_path`: in `hri_monitor/run.py`, change the `create_app(...)` call to `create_app(bus, manager, ui_dir=ROOT / "ui_dist", config_path=ROOT / "config.yaml")`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests/test_server.py -v`
Expected: all pass (4 original + 3 new). Then full suite `.venv/bin/python -m pytest tests -q` — all green.

- [ ] **Step 5: Commit**

```bash
git add hri_monitor/hub/server.py hri_monitor/run.py hri_monitor/tests/test_server.py
git commit -m "feat(api): device-control + bluetooth endpoints with persistence"
```

---

### Task 12: Backend regression + sanity

**Files:** none (verification).

- [ ] **Step 1: Full suite**

Run: `cd hri_monitor && .venv/bin/python -m pytest tests -q`
Expected: **47 passed** — bus 4, config 4, sensor_base 3, simulators 4, manager 4, frames 1, server 7, shimmer_decode 4, blink_math 2, thermal_codec 3, roi 2, cameras 1, bluetooth 1, rgb_driver 2, shimmer_driver 2, thermal_driver 3. Report the exact count (it must not have dropped any of the original 20).

- [ ] **Step 2: Hub still starts in simulator mode (no hardware deps needed)**

```bash
cd hri_monitor && .venv/bin/python run.py --no-browser & sleep 4
curl -s http://127.0.0.1:8000/api/status
curl -s http://127.0.0.1:8000/api/devices | head -c 300
kill %1
```

Expected: `/api/status` shows three simulator sensors connected; `/api/devices` returns config + options JSON. (Simulators still run because config defaults `simulate: true`.)

- [ ] **Step 3: Commit nothing / report**

```bash
git status --short
```

Expected: clean. Report backend milestone complete; UI plan (`2026-06-15-real-devices-ui.md`) is next; real-hardware smoke happens after the UI lands.
