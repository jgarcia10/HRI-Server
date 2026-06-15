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
        """Merge `updates` into config[name], rebuild and restart just that sensor."""
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
