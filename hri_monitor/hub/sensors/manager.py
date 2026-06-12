from .simulators import SimulatedRGB, SimulatedShimmer, SimulatedThermal


class SensorManager:
    """Builds sensors from config and owns their lifecycle.

    Milestone 2 will branch on cfg["simulate"] to pick real drivers; for now
    every enabled sensor gets its simulator twin.
    """

    def __init__(self, bus, config: dict):
        self.bus = bus
        self.sensors = {}
        cfg = config["sensors"]
        if cfg["shimmer"]["enabled"]:
            self.sensors["shimmer"] = SimulatedShimmer(bus)
        if cfg["thermal"]["enabled"]:
            self.sensors["thermal"] = SimulatedThermal(bus)
        if cfg["rgb"]["enabled"]:
            self.sensors["rgb"] = SimulatedRGB(bus)

    def start_all(self) -> None:
        for sensor in self.sensors.values():
            sensor.start()

    def stop_all(self) -> None:
        for sensor in self.sensors.values():
            sensor.stop()

    def statuses(self) -> dict:
        return {name: sensor.status for name, sensor in self.sensors.items()}
