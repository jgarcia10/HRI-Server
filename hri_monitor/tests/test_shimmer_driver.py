import struct

from hub.bus import MessageBus
from hub.sensors.shimmer import RealShimmer


class FakeTransport:
    """Transport seam stand-in: returns queued bytes, then b'' (no data)."""

    def __init__(self, payload=b""):
        self._buf = payload
        self.sent = []

    def send(self, data):
        self.sent.append(data)

    def read(self, n):
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk  # b'' when exhausted == "no data yet"

    def close(self):
        pass


def _frame(ppg_raw, gsr_raw, t=1000):
    t0, t1, t2 = t & 0xFF, (t >> 8) & 0xFF, (t >> 16) & 0xFF
    return bytes([0x00, t0, t1, t2]) + struct.pack("HH", ppg_raw, gsr_raw)


def test_realshimmer_construction_defaults_channel_and_port():
    s = RealShimmer(MessageBus(), mac="00:06:66:8C:4A:2C", sampling_rate=200)
    assert s.name == "shimmer" and s.mac.endswith("4A:2C") and s.sampling_rate == 200
    assert s.channel == 1 and s.port is None
    assert s.status == "disabled"


def test_realshimmer_accepts_serial_port_and_channel():
    s = RealShimmer(MessageBus(), mac="x", sampling_rate=200, channel=6, port="/dev/rfcomm13")
    assert s.channel == 6 and s.port == "/dev/rfcomm13"


def test_realshimmer_read_emits_gsr_ppg_over_transport():
    bus = MessageBus()
    got = {"gsr": [], "ppg": []}
    bus.subscribe("shimmer.gsr", lambda m: got["gsr"].append(m["data"]["value"]))
    bus.subscribe("shimmer.ppg", lambda m: got["ppg"].append(m["data"]["value"]))
    s = RealShimmer(bus, mac="x", sampling_rate=200)
    s._conn = FakeTransport(_frame(2048, 2000))  # inject; bypass connect()
    s.read()
    assert len(got["ppg"]) == 1 and got["ppg"][0] > 0
    assert len(got["gsr"]) == 1 and got["gsr"][0] > 0


def test_realshimmer_read_no_data_is_noop_not_error():
    # b'' from the transport (read timeout) must NOT raise — the watchdog handles
    # staleness via _last_emit; a transient empty read is normal.
    s = RealShimmer(MessageBus(), mac="x")
    s._conn = FakeTransport(b"")  # nothing available
    s.read()  # should return cleanly


def test_realshimmer_handshake_waits_for_ack():
    # connect() drives the handshake over the transport: each command is followed
    # by an ACK (0xFF). A transport pre-loaded with ACKs lets us drive it without
    # opening a real socket/serial port.
    s = RealShimmer(MessageBus(), mac="x", sampling_rate=200)
    ack_stream = FakeTransport(b"\xff\xff\xff\xff")
    s._open_transport = lambda: ack_stream  # stub the real transport factory
    s.connect()
    # four config commands were sent (set sensors, expansion power, rate, start)
    assert len(ack_stream.sent) == 4
