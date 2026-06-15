import io
import os

import numpy as np

from hub.bus import MessageBus
from hub.sensors.thermal import ThermalProcess
from hub.sensors.thermal_codec import encode_message


def test_thermalprocess_construction():
    s = ThermalProcess(MessageBus(), xml="15030138.xml",
                       detector="d.svm", predictor="p.dat", format_dir="/tmp/x")
    assert s.name == "thermal" and s.xml == "15030138.xml"
    assert s.status == "disabled"


def _pipe_with(data: bytes):
    r, w = os.pipe()
    if data:
        os.write(w, data)
    os.close(w)  # EOF after data
    return os.fdopen(r, "rb")


def test_thermalprocess_read_emits_from_pipe():
    bus = MessageBus()
    temps_got, frame_got = [], []
    bus.subscribe("thermal.temps", lambda m: temps_got.append(m["data"]))
    bus.subscribe("thermal.frame", lambda m: frame_got.append(m["data"]["frame"]))
    s = ThermalProcess(bus, xml="x", detector="d", predictor="p", format_dir="/tmp")
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    s._stdout = _pipe_with(encode_message({"nose": 31.2}, frame))
    s.read()
    assert temps_got == [{"nose": 31.2}]
    assert frame_got[0].shape == (4, 4, 3)


def test_thermalprocess_read_raises_on_worker_death():
    s = ThermalProcess(MessageBus(), xml="x", detector="d", predictor="p", format_dir="/tmp")
    s._stdout = _pipe_with(b"")  # immediate EOF = worker died
    try:
        s.read()
        raised = False
    except Exception:
        raised = True
    assert raised


def test_thermalprocess_read_times_out_when_silent():
    s = ThermalProcess(MessageBus(), xml="x", detector="d", predictor="p", format_dir="/tmp")
    s.read_timeout = 0.3  # fast for the test
    r, w = os.pipe()  # write end stays open but nothing is written → silent worker
    s._stdout = os.fdopen(r, "rb")
    import time as _t
    t0 = _t.monotonic()
    try:
        s.read()
        raised = False
    except Exception:
        raised = True
    elapsed = _t.monotonic() - t0
    os.close(w)
    assert raised and elapsed < 2.0  # bounded, did not hang
