"""Real Shimmer GSR+ over a Bluetooth RFCOMM socket (stdlib). Config handshake
and decode ported from hri_server.py shimmer_main/data_read_loop."""
import socket
import struct
import time

from .base import BaseSensor
from .shimmer_decode import FRAMESIZE, HeartRate, clock_wait_for_rate, decode_frame

ACK = struct.pack("B", 0xFF)


class RealShimmer(BaseSensor):
    name = "shimmer"
    stale_after = 3.0

    def __init__(self, bus, mac=None, sampling_rate=200, connect_timeout=10.0):
        super().__init__(bus)
        self.mac = mac
        self.sampling_rate = sampling_rate
        self.connect_timeout = connect_timeout
        self._sock = None
        self._hr = HeartRate(fs=sampling_rate)
        self._buf = b""

    def _wait_ack(self):
        while True:
            b = self._sock.recv(1)
            if not b:
                raise RuntimeError("socket closed during handshake")
            if b == ACK:
                return

    def connect(self):
        if not self.mac:
            raise RuntimeError("no Bluetooth MAC configured")
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        s.settimeout(self.connect_timeout)
        s.connect((self.mac, 1))  # RFCOMM channel 1 (SPP)
        self._sock = s
        s.sendall(struct.pack("BBBB", 0x08, 0x04, 0x01, 0x00)); self._wait_ack()
        s.sendall(struct.pack("BB", 0x5E, 0x01)); self._wait_ack()
        s.sendall(struct.pack("<BH", 0x05, clock_wait_for_rate(self.sampling_rate))); self._wait_ack()
        s.sendall(struct.pack("B", 0x07)); self._wait_ack()
        s.settimeout(2.0)  # read timeout so a dead sensor trips the watchdog
        self._buf = b""

    def read(self):
        while len(self._buf) < FRAMESIZE:
            chunk = self._sock.recv(FRAMESIZE - len(self._buf))
            if not chunk:
                raise RuntimeError("shimmer socket closed")
            self._buf += chunk
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
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
