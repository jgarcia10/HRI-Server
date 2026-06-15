"""Real Shimmer GSR+ driver. Reads the same 8-byte frames over either:
  - a bound RFCOMM serial port (e.g. /dev/rfcomm13) via pyserial — the proven
    path (matches the working shimmer_server.py + `rfcomm connect ... <channel>`), or
  - a direct Bluetooth RFCOMM socket on a configurable channel (no rfcomm bind).
Set `port` to use serial; otherwise the socket is used with `channel` (SPP channel,
device-specific — many Shimmer3 units present SPP on channel 1, some on others).
Config handshake and decode ported from hri_server.py shimmer_main/data_read_loop."""
import struct
import time

from .base import BaseSensor
from .shimmer_decode import FRAMESIZE, HeartRate, clock_wait_for_rate, decode_frame

ACK = b"\xff"


class _SocketTransport:
    """Raw AF_BLUETOOTH RFCOMM socket. read() returns b'' on timeout, raises
    ConnectionError on peer close."""

    def __init__(self, mac, channel, connect_timeout):
        import socket

        self._socket = socket
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        s.settimeout(connect_timeout)
        s.connect((mac, channel))
        s.settimeout(2.0)  # read timeout so a dead sensor trips the watchdog
        self._s = s

    def send(self, data):
        self._s.sendall(data)

    def read(self, n):
        try:
            data = self._s.recv(n)
        except self._socket.timeout:
            return b""  # no data this cycle
        if data == b"":
            raise ConnectionError("shimmer socket closed by peer")
        return data

    def close(self):
        try:
            self._s.close()
        except Exception:
            pass


class _SerialTransport:
    """Bound RFCOMM tty via pyserial (proven path). read() returns up to n bytes,
    b'' on timeout, raises ConnectionError on a device error/unplug."""

    def __init__(self, port, connect_timeout):
        import serial  # pyserial; lazy so the hub starts without it

        self._serial = serial
        self._ser = serial.Serial(port, 115200, timeout=1)
        self._ser.reset_input_buffer()

    def send(self, data):
        self._ser.write(data)

    def read(self, n):
        try:
            return self._ser.read(n)  # up to n; b'' on timeout
        except self._serial.SerialException as e:
            raise ConnectionError(f"shimmer serial error: {e}")

    def close(self):
        try:
            self._ser.close()
        except Exception:
            pass


class RealShimmer(BaseSensor):
    name = "shimmer"
    stale_after = 4.0

    def __init__(self, bus, mac=None, sampling_rate=200, channel=1, port=None, connect_timeout=10.0):
        super().__init__(bus)
        self.mac = mac
        self.sampling_rate = sampling_rate
        self.channel = channel
        self.port = port  # serial device path; if set, use serial instead of socket
        self.connect_timeout = connect_timeout
        self._conn = None
        self._hr = HeartRate(fs=sampling_rate)
        self._buf = b""

    def _open_transport(self):
        """Build the transport from config. Overridable in tests."""
        if self.port:
            return _SerialTransport(self.port, self.connect_timeout)
        if self.mac:
            return _SocketTransport(self.mac, self.channel, self.connect_timeout)
        raise RuntimeError("Shimmer needs a serial port (bind /dev/rfcommN) or a Bluetooth MAC")

    def _wait_ack(self, deadline):
        while time.monotonic() < deadline:
            b = self._conn.read(1)
            if b == ACK:
                return
            # ignore non-ACK / empty reads and keep waiting until the deadline
        raise TimeoutError("no ACK from Shimmer during configuration")

    def connect(self):
        self._conn = self._open_transport()
        self._buf = b""
        deadline = time.monotonic() + self.connect_timeout
        # Configure: set GSR+PPG sensors, enable expansion power, set rate, start.
        self._conn.send(struct.pack("BBBB", 0x08, 0x04, 0x01, 0x00)); self._wait_ack(deadline)
        self._conn.send(struct.pack("BB", 0x5E, 0x01)); self._wait_ack(deadline)
        self._conn.send(struct.pack("<BH", 0x05, clock_wait_for_rate(self.sampling_rate))); self._wait_ack(deadline)
        self._conn.send(struct.pack("B", 0x07)); self._wait_ack(deadline)

    def read(self):
        data = self._conn.read(FRAMESIZE - len(self._buf))
        if data:
            self._buf += data
        while len(self._buf) >= FRAMESIZE:
            frame, self._buf = self._buf[:FRAMESIZE], self._buf[FRAMESIZE:]
            s = decode_frame(frame)
            t = time.time()
            self.emit("shimmer.gsr", {"value": s["gsr"]})
            self.emit("shimmer.ppg", {"value": s["ppg"]})
            hr = self._hr.update(s["ppg"], t)
            if hr:
                bpm, hrv = hr
                self.emit("ppg.hr", {"value": bpm})
                self.emit("ppg.hrv", {"value": hrv})

    def disconnect(self):
        if self._conn is not None:
            try:
                self._conn.send(struct.pack("B", 0x20))  # stop streaming (best-effort)
            except Exception:
                pass
            self._conn.close()
            self._conn = None
