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
    assert frame.dtype == np.uint8
    assert set(temps) == {"forehead", "left_cheek", "right_cheek", "nose"}
    assert all(25.0 < v < 40.0 for v in temps.values())


def test_simulated_rgb_emits_frame_and_blink():
    got = collect(SimulatedRGB, ["rgb.frame", "rgb.blink"])
    frame = got["rgb.frame"][0]["data"]["frame"]
    blink = got["rgb.blink"][0]["data"]
    assert isinstance(frame, np.ndarray) and frame.shape == (240, 320, 3)
    assert frame.dtype == np.uint8
    assert blink["rate"] >= 0.0
    assert 0.0 < blink["ear"] < 1.0


def test_simulators_emit_a_fresh_frame_each_read():
    bus = MessageBus()
    frames = []
    bus.subscribe("thermal.frame", lambda m: frames.append(m["data"]["frame"]))
    sensor = SimulatedThermal(bus)
    sensor.connect()
    sensor.read()
    sensor.read()
    assert frames[0] is not frames[1]
