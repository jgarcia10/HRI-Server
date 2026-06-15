# HRI Monitor — Milestone 2: Real Device Drivers & Devices Page

**Date:** 2026-06-15
**Status:** Approved pending user review
**Scope:** `hri_monitor/` — real RGB/thermal/Shimmer drivers behind the existing `BaseSensor`/`SensorManager`/bus contract, a device-control REST API with config persistence and hot-reconfigure, and a Devices page (Clinical Frost). Builds on milestone 1 (foundation) and the Clinical Frost UI.

## 1. Goal

Replace the three simulator twins with real hardware drivers, each configurable and connectable entirely from the web Devices page:

1. **RGB camera** — USB webcam by V4L2 index → MediaPipe blink/EAR (ports `hri_server.py` `blink_loop`).
2. **Thermal camera** — USB Optris via the irdirect SDK + XML calibration → dlib facial ROI temperatures (ports `capture_loop`), run in an **isolated subprocess**.
3. **Shimmer GSR/PPG** — Bluetooth: in-app scan → pair → RFCOMM-socket stream, + HR/HRV from PPG (ports `shimmer_main`/`data_read_loop`).

The simulator path remains fully working; "real" is selected per device. Real means real — devices never silently fall back to simulation.

## 2. Decisions (from brainstorming)

- **Bluetooth:** in-app scan + pair + connect. `bluetoothctl` (subprocess) for discovery/pair/trust; data via a Python stdlib RFCOMM socket (`AF_BLUETOOTH`/`BTPROTO_RFCOMM`) — no `rfcomm bind`, no fixed `/dev/rfcommN`. Shimmer3 classic PIN 1234 handled/hinted.
- **Failure behavior:** real-only. On failure the watchdog retries and the UI shows the device red with a reason; NO automatic simulator fallback. A per-device Real⇄Simulator toggle is the explicit opt-in to simulation.
- **Dependencies:** `dlib`, `mediapipe`, `pyserial` added to `requirements.txt`, BUT each real driver imports its heavy deps **lazily inside `connect()`**, so a missing/broken dep degrades to that one device showing "driver unavailable: <reason>" rather than breaking hub startup.
- **Apply model:** hot-apply + persist. Config changes from the UI restart just that sensor live AND save to `config.yaml`.
- **Thermal hosting:** isolated subprocess from the start (native SDK can segfault; must not take down the web server).

## 3. Architecture

The `BaseSensor` contract, `SensorManager`, bus, `FrameStore`, WS, and Live page are unchanged. Real drivers emit the identical topics/payloads the simulators emit:
`rgb.frame {frame}`, `rgb.blink {rate, ear}`, `thermal.frame {frame}`, `thermal.temps {forehead,left_cheek,right_cheek,nose}`, `shimmer.gsr {value}`, `shimmer.ppg {value}`, plus new `ppg.hr {value}`, `ppg.hrv {value}` (both already in `server.STREAM_TOPICS`).

Hosting per device:
- **RGB** (`hub/sensors/rgb.py` → `RealRGB`) — in-process watchdog thread.
- **Shimmer** (`hub/sensors/shimmer.py` → `RealShimmer`) — in-process watchdog thread (RFCOMM socket).
- **Thermal** (`hub/sensors/thermal.py` → `ThermalProcess` proxy + `hub/sensors/thermal_worker.py`) — proxy is a `BaseSensor` thread that spawns and reads from a subprocess running the SDK.

### Files

```
hri_monitor/
├── requirements.txt                 # + dlib, mediapipe, pyserial
├── hub/
│   ├── config.py                    # + save_config()
│   ├── server.py                    # + device-control & bluetooth REST endpoints
│   ├── bluetooth.py                 # NEW: bluetoothctl wrapper + serial-port list
│   ├── cameras.py                   # NEW: V4L2 device enumeration (/dev/video* + names)
│   └── sensors/
│       ├── base.py                  # unchanged
│       ├── simulators.py            # unchanged
│       ├── manager.py               # real-vs-sim factory + reconfigure/restart/connect/disconnect
│       ├── rgb.py                   # NEW: RealRGB
│       ├── shimmer.py               # NEW: RealShimmer + GSR/PPG/HR/HRV decode
│       ├── thermal.py               # NEW: ThermalProcess proxy + framing codec
│       └── thermal_worker.py        # NEW: standalone Optris-SDK + dlib subprocess
└── ui/src/
    ├── pages/Devices.tsx            # NEW
    ├── components/DeviceCard.tsx    # NEW
    ├── components/BluetoothScan.tsx # NEW
    └── lib/devices.ts               # NEW: useDevices() hook + API calls
```

## 4. Drivers

### 4.1 RealRGB (`hub/sensors/rgb.py`)
- `connect()`: lazy-import `cv2`, `mediapipe`; `cv2.VideoCapture(index, cv2.CAP_V4L2)`; set width/height/fps from config; raise if `not cap.isOpened()`; create FaceMesh(max_num_faces=1, refine_landmarks=True).
- `read()`: grab frame; raise on read failure (trips watchdog); FaceMesh → left/right EAR from landmark indices `[33,160,158,133,153,144]` / `[362,385,387,263,373,380]`; weighted blink rate = `0.1*cumulative + 0.7*sliding(5s) + 0.2*instant` (port of `blink_loop`); draw eye points + EAR; emit `rgb.frame` (annotated) and `rgb.blink {rate, ear}`.
- `disconnect()`: release capture, close FaceMesh; idempotent.

### 4.2 Thermal (`thermal_worker.py` + `thermal.py`)
- **Worker** `python -m hub.sensors.thermal_worker --xml <f> [--detector <svm>] [--predictor <dat>] [--format-dir <dir>]`:
  - Loads `libirdirectsdk` (ctypes), `evo_irimager_usb_init(xml, format_dir, log)`, reads thermal + palette sizes, loops `evo_irimager_get_thermal_palette_image_metadata`.
  - Temperature map `= thermal/10 - 100`; palette → BGR display image.
  - dlib `simple_object_detector` + `shape_predictor` (thermal-trained models), re-detect every 5 s; `RegionsOfInterest` → forehead/left_cheek/right_cheek/nose; scale ROI to thermal array; mean temp per ROI; last-valid fallback for momentarily-empty temps (port of `capture_loop`).
  - Each iteration writes one framed message to stdout: `4-byte big-endian length` + `length bytes` of `[4-byte meta-len][JSON meta {temps, w, h, dtype}][raw BGR bytes]`.
  - On fatal init error: print reason to stderr, exit non-zero.
- **Proxy** `ThermalProcess(BaseSensor)`:
  - `connect()`: lazy-check assets exist; `subprocess.Popen([sys.executable, "-m", "hub.sensors.thermal_worker", ...], stdout=PIPE, stderr=PIPE)`; read first framed message within a timeout (proves init); on timeout/EOF raise with captured stderr.
  - `read()`: read one framed message (with timeout via non-blocking/`select`); decode; emit `thermal.temps` + `thermal.frame`. Raise on EOF/short read (worker died) → watchdog respawns.
  - `disconnect()`: terminate worker (SIGTERM, then SIGKILL after grace), drain pipes; idempotent.
- **Codec** (`thermal.py`): `encode_message(temps, frame) -> bytes` / `decode_message(reader) -> (temps, frame)` — pure, unit-tested round-trip.

### 4.3 RealShimmer (`hub/sensors/shimmer.py`)
- `connect()`: lazy-import nothing heavy (stdlib `socket`, `struct`); `s = socket.socket(AF_BLUETOOTH, SOCK_STREAM, BTPROTO_RFCOMM)`; `s.settimeout(connect_timeout)`; `s.connect((mac, 1))`; run config handshake (inquiry/sensors `0x08,0x04,0x01,0x00`; `0x5E,0x01`; sampling rate `0x05 + clock_wait` where `clock_wait=int((2<<14)/sampling_rate)`; start `0x07`), each followed by ACK `0xFF` wait (port of `shimmer_main`); set a read timeout on the socket.
- `read()`: read one 8-byte frame; decode timestamp + PPG_raw/GSR_raw; GSR range/Rf table `[40.2,287.0,1000.0,3300.0]`; `GSR_muS`, `PPG_mv` (port of `data_read_loop`); push PPG to a rolling buffer, derive heart rate (peak intervals) + RMSSD HRV; emit `shimmer.gsr {value}`, `shimmer.ppg {value}`, and when enough beats: `ppg.hr {value}`, `ppg.hrv {value}`. Socket timeout → watchdog.
- `disconnect()`: best-effort stop command + close socket; idempotent.
- **Decode helpers** are module-level pure functions, unit-tested against known bytes.

### 4.4 Bluetooth helper (`hub/bluetooth.py`)
- `scan(seconds=8) -> list[{name, mac, paired}]` — drive `bluetoothctl` (scan on / devices / paired-devices), parse output.
- `pair(mac, pin="1234") -> {ok, reason}` — `bluetoothctl pair`/`trust`, feed PIN if agent prompts, with timeout.
- `list_serial_ports() -> list[str]` — fallback path (`/dev/rfcomm*`, `/dev/ttyUSB*`).
- All subprocess calls have timeouts; output parsing is unit-tested against captured fixtures.

### 4.5 Camera enumeration (`hub/cameras.py`)
- `list_cameras() -> list[{index, path, name}]` — enumerate `/dev/video*`, read names via V4L2 (sysfs `/sys/class/video4linux/videoN/name` as a dependency-free source). Unit-tested against a fake sysfs tree.

## 5. SensorManager changes

- `_build(name, cfg) -> BaseSensor`: factory choosing `Real*` vs `Simulated*` by `cfg["sensors"][name]["simulate"]`, passing device params.
- Constructor uses `_build` for each enabled sensor (replaces hardcoded simulator construction).
- `reconfigure(name, new_cfg)`: under a lock — stop the one sensor, rebuild via `_build`, start it. Other sensors and the server are unaffected.
- `restart(name)` / `connect(name)` / `disconnect(name)`: single-sensor lifecycle.
- `sensors` dict access guarded by a lock (control endpoints run on request threads).

## 6. REST API (`hub/server.py`)

- `GET /api/devices` → per device `{config, status, options}` where options include enumerated cameras, XML files + detected serials, sampling-rate choices, and `driver_available` (deps importable).
- `POST /api/devices/{name}/config` body `{simulate?, index?, width?, height?, fps?, xml?, mac?, sampling_rate?}` → validate, `save_config`, `manager.reconfigure`.
- `POST /api/devices/{name}/restart` · `/connect` · `/disconnect`.
- `POST /api/bluetooth/scan` → `bluetooth.scan()`.
- `POST /api/bluetooth/pair` body `{mac, pin?}` → `bluetooth.pair()`.
Existing `/api/status`, `/ws`, `/stream/{feed}`, static mount unchanged.

## 7. Config & persistence

- `config.py` gains `save_config(path, cfg)` (YAML dump; comments not preserved — acceptable for a generated file).
- New/used keys: `rgb.{simulate,index,width,height,fps}`, `thermal.{simulate,xml,detector,predictor,format_dir}`, `shimmer.{simulate,mac,sampling_rate}`. Asset path keys default to the existing repo locations; large dlib models are NOT copied into `hri_monitor/` nor committed.
- `POST .../config` updates in-memory config and persists, surviving relaunch.

## 8. Devices page (`ui/`)

- `Devices.tsx`: three `DeviceCard`s, replacing the sidebar placeholder.
- `DeviceCard.tsx`: header (icon + name + `StatusChip`), config controls, Connect/Disconnect/Restart, Real⇄Simulator toggle. Thermal = XML select + serial/res + dlib status; RGB = `/dev/videoN` select + resolution/fps; Shimmer = sampling-rate select + `BluetoothScan`.
- `BluetoothScan.tsx`: Scan → discovered list (name + MAC + paired badge) → Pair (PIN 1234 hint) → connect.
- `lib/devices.ts`: `useDevices()` polls `GET /api/devices` (~1 s); action helpers POST config/lifecycle/bluetooth; optimistic in-flight states. Live status continues via `/ws` `devices`.
- Clinical Frost tokens only; reuses `StatusChip`. Rebuilt `ui_dist` committed.

## 9. Error handling

- Real `connect()` raises readable exceptions (camera busy, socket refused/timeout, SDK init code, missing dep/asset) → watchdog → red status + reason in the UI.
- Missing dlib/Optris/XML/dlib-model → "driver unavailable" / "asset not found", hub still runs.
- Thermal worker stderr captured + logged; worker crash → proxy `read()` raises → respawn.
- Bluetooth scan/pair failures return structured `{ok:false, reason}` to the UI.
- All hardware I/O uses timeouts; nothing blocks the watchdog or a request indefinitely.
- No automatic simulator fallback.

## 10. Testing

Hardware-free by design (CI has no devices):
- **Decode/logic units:** GSR/PPG byte decode (known bytes → known µS/mV), EAR + weighted blink-rate math, ROI geometry/scaling, HR/HRV from a synthetic PPG buffer, thermal framing codec round-trip, `bluetoothctl` output parsing (captured fixtures), camera enumeration (fake sysfs).
- **Manager:** `_build` real-vs-sim selection (without opening hardware — assert class type), `reconfigure` swaps a sensor live, `save_config`/`load_config` round-trip.
- **API:** `/api/devices`, config POST persists + reconfigures, bluetooth endpoints call the helper — via a fake manager (existing server-test pattern).
- Existing 20 simulator tests stay green. Real drivers are NOT opened in tests; lazy imports keep collection working without dlib/mediapipe present.
- Manual hardware smoke (real rig) documented as the plan's final task: connect each device from the Devices page, confirm live data + persistence + hot-reconfigure.

## 11. Out of scope

- ROS adapters (milestone 4), CL/T model plugins (milestone 3), experiments/recording (milestone 5), statistics (milestone 6).
- Windows/macOS device backends (Linux V4L2 + BlueZ + irdirect only).
- Auto-installing system packages or build tools; privileged helpers (assumes the user is in `video`/`dialout`/`bluetooth` groups for hardware access).
- Multi-camera fusion, GPU acceleration, recording of raw video.
