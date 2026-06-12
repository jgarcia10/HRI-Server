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
