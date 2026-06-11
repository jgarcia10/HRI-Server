# HRI Monitor Platform — Design Spec

**Date:** 2026-06-11
**Status:** Approved pending user review
**Replaces:** `hri_server.py` (Flask monolith), `cognitive-load-dashboard_react` (Next.js UI), `cognitive_trust_dashboard_django` (Django API). These remain untouched as references; the new platform is built from scratch.

## 1. Goal

A single-folder, locally run, no-auth web platform (`hri_monitor/`) for human-robot interaction studies that:

1. Acquires physiological signals directly from hardware, configurable from the UI:
   - **Optris thermal camera** — selected by serial number / XML calibration file (Optris SDK).
   - **RGB camera** — selected by V4L2 device index.
   - **Shimmer GSR+ sensor** — selected via Bluetooth scan (name/MAC), connected over an RFCOMM socket (no external `rfcomm bind` required), with configurable sampling rate (default 200 Hz).
2. Computes live signals: facial ROI temperatures (forehead, left/right cheek, nose), blink rate / EAR eye metrics, GSR (µS), raw PPG, heart rate and HRV from PPG peaks.
3. Communicates with **both ROS 1 and ROS 2 natively** — publishing sensor streams and cognitive load / trust estimates, subscribing to user-selected robot/task topics (optional) recorded as aligned events.
4. Hosts **pluggable online models** estimating Cognitive Load (CL) and Trust (T) indices from a sliding feature window.
5. Manages **experiments** (participant → session → condition recordings with timestamped markers) for data collection.
6. Runs **statistical comparisons between conditions** (standard inferential suite) inside the platform.

Launch: `python run.py` → hub starts, available ROS adapters spawn, browser opens at `http://localhost:8000`.

## 2. Architecture (chosen: Hub + ROS adapter processes)

Rationale: rospy (ROS 1) and rclpy (ROS 2) cannot share a Python process/environment. The hub stays ROS-free; each adapter runs in its own sourced ROS environment as a subprocess.

```
┌─────────────────────────────────────────────┐
│  hub (one Python process, no ROS imports)   │
│  FastAPI ── WebSocket/MJPEG/REST ── React UI│
│  Sensor threads: Optris · RGB · Shimmer     │
│   (each with watchdog + auto-reconnect)     │
│  Feature engine · Model plugins · SQLite    │
│  Local message bus (JSON over WebSocket)    │
└────────┬───────────────────────┬────────────┘
         │                       │
┌────────┴────────┐     ┌────────┴────────┐
│ ros2_adapter.py │     │ ros1_adapter.py │
│ (rclpy env)     │     │ (rospy env)     │
└─────────────────┘     └─────────────────┘
```

- `run.py` probes known ROS setup files (e.g., `/opt/ros/<distro>/setup.bash`), launches each enabled adapter via `bash -c "source <setup> && python adapters/<name>.py --hub ws://127.0.0.1:8000/bus"`.
- Adapter ↔ hub protocol: JSON over local WebSocket — `hello` (capabilities), `publish` (topic data out to ROS), `subscribe` (request ROS topic), `event` (incoming ROS message). Binary frames are not sent to adapters (video stays in the hub).
- The hub is fully functional with zero adapters (no ROS installed).
- Future escape hatch: if the Optris SDK proves unstable, only the thermal driver is promoted to a worker subprocess; nothing else changes.

### Folder layout

```
hri_monitor/
├── run.py                  # single entry point
├── requirements.txt
├── config.yaml             # device defaults, ports, paths (editable in UI)
├── hub/
│   ├── server.py           # FastAPI: REST + /ws + MJPEG + /bus (adapter endpoint)
│   ├── bus.py              # in-process pub/sub
│   ├── sensors/            # base.py (watchdog), optris.py, rgb_camera.py, shimmer.py, simulators
│   ├── processing/         # thermal face ROIs, blink/EAR, PPG→HR/HRV, feature windows
│   ├── models/             # plugin loader + baseline_model.py
│   ├── experiments/        # SQLite schema + session recorder
│   └── analysis/           # feature extraction + inferential statistics
├── adapters/
│   ├── ros2_adapter.py     # rclpy
│   └── ros1_adapter.py     # rospy
├── ui/                     # React + Vite + Tailwind source (dev only)
├── ui_dist/                # built frontend, committed — runtime needs Python only
├── assets/                 # dlib models, Optris XML calibration files
└── data/                   # hri.db (SQLite) + per-session Parquet/CSV signal files
```

## 3. Sensor layer

Common contract (`sensors/base.py`): a sensor thread produces timestamped samples onto the bus, exposes `status` (`connected / reconnecting / disconnected / disabled`), and is supervised by a watchdog — no data for N seconds → close, reconnect with exponential backoff. Each sensor is individually start/stop/reconfigurable from the UI without restarting the app. Every sensor has a **simulator twin** (synthetic GSR/PPG, fake thermal frames containing a face, prerecorded RGB loop) selectable in Settings, so the entire pipeline runs with no hardware.

- **Optris thermal** (`optris.py`): loads `libirdirectsdk` guardedly (missing lib/XML → visible error, not a crash). Scans `assets/*.xml` and connected camera serials; user picks one. Produces raw palette frames, overlay frames, and a radiometric temperature map. Face detection: dlib detector + landmark predictor (from `assets/`), re-detection every 5 s as today; ROI extraction logic ported from `hri_server.py` (`RegionsOfInterest`).
- **RGB camera** (`rgb_camera.py`): enumerates `/dev/video*` with device names via V4L2; user picks index, resolution, FPS. MediaPipe FaceMesh → EAR, weighted blink rate (same 0.1/0.7/0.2 cumulative/sliding/instantaneous weighting as today), annotated frames.
- **Shimmer GSR+** (`shimmer.py`): UI-triggered Bluetooth scan (bluetoothctl/dbus); user picks device; hub connects via `socket(AF_BLUETOOTH, SOCK_STREAM, BTPROTO_RFCOMM)` directly. Streaming protocol and GSR/PPG conversion ported from `hri_server.py` (`shimmer_main`/`data_read_loop`). Sampling rate configurable (default 200 Hz). PPG → heart rate and RMSSD HRV via peak detection over a sliding window.

## 4. Real-time data flow

Internal bus topics: `thermal.temps`, `thermal.frame`, `rgb.frame`, `rgb.blink`, `shimmer.gsr`, `shimmer.ppg`, `ppg.hr`, `ppg.hrv`, `model.estimates`, `device.status`, `ros.event`.

Consumers:
1. **Dashboard WebSocket `/ws`** — numeric signals decimated to ~10 Hz, device status, CL/T estimates, recording state.
2. **MJPEG** — `/stream/thermal` (ROI overlays), `/stream/thermal/raw`, `/stream/rgb` (landmarks overlay).
3. **Feature engine** — sliding window (default 30 s, configurable), emits a feature vector at 1 Hz: GSR tonic/phasic stats, HR/HRV, blink rate, per-ROI temperatures + slopes (incl. nose–forehead delta).
4. **Recorder** — when armed, writes all raw samples to a per-recording Parquet file (incremental flush ~1 s) and metadata to SQLite; CSV export on demand.

## 5. CL/T model plugins

`hub/models/` is scanned for plugins. Contract:

```python
class Model:
    name = "my_model"
    def predict(self, features: FeatureWindow) -> dict:
        return {"cognitive_load": 0.42, "trust": 0.71}  # both in [0, 1]
```

- Any Python file (sklearn, torch, rules) may implement it; UI lists discovered plugins and switches the active one live.
- Ships with `baseline_model.py`: transparent normalized heuristic over GSR + blink rate + nose temperature, so estimates flow on day one.
- Estimates go to the dashboard, into recordings, and out through ROS adapters.
- A plugin raising an exception is deactivated with a visible error; the platform keeps running.

## 6. ROS integration

Both adapters expose the same surface, in their own environments:

**Published topics** (names configurable, defaults): `hri/gsr`, `hri/ppg`, `hri/heart_rate`, `hri/blink_rate` (Float32); `hri/facial_temperature` (Float32MultiArray: forehead, left cheek, right cheek, nose); `hri/cognitive_load`, `hri/trust` (Float32).

**Subscriptions**: user configures a list of topics + types in the UI (common std_msgs types supported); incoming messages become timestamped `ros.event` records aligned with physiological data — used for robot/task event annotation (optional feature; everything works without it).

Adapters reconnect to the hub automatically; adapter death is shown in the UI and never affects the hub.

## 7. Experiments & data model (SQLite)

- **Experiment** — name, description, ordered list of named conditions.
- **Participant** — anonymized code, notes.
- **Session** — participant × experiment, date.
- **Recording** — one condition run within a session: condition, start/stop timestamps, Parquet path, active model name.
- **Marker** — timestamped label dropped from the UI during recording (e.g., "robot error").

Live page workflow: select experiment/participant/condition → Start → pinned recording bar (elapsed time, condition, marker button) → Stop. Interrupted recordings remain analyzable (incremental flush).

## 8. Statistical analysis

Analysis page: pick experiment → signal/feature → conditions.

Pipeline per comparison:
1. Per-recording feature extraction (mean, SD, slope, min/max, peaks/min for the chosen signal).
2. Shapiro–Wilk normality check.
3. Automatic test selection: 2 conditions → paired/unpaired t-test or Wilcoxon/Mann–Whitney; 3+ → repeated-measures ANOVA or Friedman, with post-hoc pairwise tests (Holm correction).
4. Effect sizes: Cohen's d / rank-biserial correlation.
5. Box/violin plots per condition in the UI; results table.
6. Export: tidy per-recording CSV + results table.

Guard: fewer than 3 recordings per condition → "insufficient data" message instead of statistics.

## 9. UI (chosen: Hybrid — dark theme + sidebar)

Stack: React + Vite + Tailwind, shadcn-style components, Recharts for charts. Built output committed to `ui_dist/` and served by FastAPI — Node is needed only to develop the UI.

Pages (sidebar):
- **Live** — dense mission-control view: thermal + RGB feeds, CL/T gauges, signal strips (GSR, HR, blink, 4×temperature), pinned recording bar.
- **Devices** — per-device cards: thermal (XML/serial picker), RGB (index/resolution picker), Shimmer (BT scan/connect, sampling rate), ROS adapters (env detection, topic config); live status + restart buttons; simulator toggles.
- **Experiments** — CRUD for experiments/conditions/participants; session browser; per-recording detail with marker timeline; CSV/Parquet export.
- **Analysis** — condition comparison UI (section 8).
- **Models** — plugin list, active model selector, live estimate preview, plugin error display.
- **Settings** — window sizes, ports, data directory, theme.

## 10. Error handling principles

- A sensor problem never takes down the platform; all failures surface as UI status.
- Guarded native-library loading (Optris SDK) with actionable error messages.
- Watchdog + auto-reconnect on every sensor; adapter auto-reconnect to hub.
- Incremental recording flush (≤ ~1 s data loss on crash).
- Statistics refuse to run on insufficient data rather than producing misleading output.

## 11. Testing

- **Hardware-free pipeline**: simulator twins per sensor make the full chain (bus → features → model → recorder → analysis → UI) runnable and demoable with no devices.
- **Pytest**: feature engine correctness, model plugin contract (load/switch/failure), recorder integrity (flush/crash recovery), statistics validated against known SciPy results.
- **Adapters**: protocol-level tests over the JSON/WebSocket bus without ROS installed; manual smoke test with real ROS for releases.

## 12. Out of scope

- Authentication / multi-user.
- Remote/cloud deployment.
- Training models inside the platform (plugins are trained elsewhere and dropped in).
- ROS 1 ↔ ROS 2 bridging between robots (each adapter talks to its own ROS world).
- Migration of data from the old Django/React projects.
