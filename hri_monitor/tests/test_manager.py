import copy
import copy as _copy

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
