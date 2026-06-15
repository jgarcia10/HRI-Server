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
