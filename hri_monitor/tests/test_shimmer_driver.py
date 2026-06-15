import struct

from hub.bus import MessageBus
from hub.sensors.shimmer import RealShimmer


class FakeSock:
    def __init__(self, payload):
        self._buf = payload
    def recv(self, n):
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk
    def settimeout(self, t): pass
    def close(self): pass


def test_realshimmer_construction():
    s = RealShimmer(MessageBus(), mac="00:06:66:8C:4A:2C", sampling_rate=200)
    assert s.name == "shimmer" and s.mac.endswith("4A:2C") and s.sampling_rate == 200
    assert s.status == "disabled"


def test_realshimmer_read_emits_gsr_ppg():
    bus = MessageBus()
    got = {"gsr": [], "ppg": []}
    bus.subscribe("shimmer.gsr", lambda m: got["gsr"].append(m["data"]["value"]))
    bus.subscribe("shimmer.ppg", lambda m: got["ppg"].append(m["data"]["value"]))
    s = RealShimmer(bus, mac="x", sampling_rate=200)
    frame = bytes([0x00, 0xE8, 0x03, 0x00]) + struct.pack("HH", 2048, 2000)
    s._sock = FakeSock(frame)  # inject; bypass connect()
    s.read()
    assert len(got["ppg"]) == 1 and got["ppg"][0] > 0
    assert len(got["gsr"]) == 1 and got["gsr"][0] > 0
