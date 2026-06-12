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


def test_backoff_grows_when_connected_but_silent():
    """A device that connects fine but never emits must back off exponentially."""
    bus = MessageBus()
    reconnects = []
    bus.subscribe("device.status",
                  lambda m: reconnects.append(time.time()) if m["data"]["status"] == "reconnecting" else None)

    class SilentFast(BaseSensor):
        name = "silentfast"
        stale_after = 0.05
        initial_backoff = 0.05
        max_backoff = 1.0

        def connect(self):
            pass

        def read(self):
            time.sleep(0.01)

    sensor = SilentFast(bus)
    sensor.start()
    try:
        assert wait_for(lambda: len(reconnects) >= 4, timeout=5.0)
    finally:
        sensor.stop()
    # gaps between consecutive reconnecting transitions must grow
    gaps = [b - a for a, b in zip(reconnects, reconnects[1:4])]
    assert gaps[-1] > gaps[0] * 1.5
