"""Gripper actuators for the UR backend.

The OnRobot RG2 v2 on the study's CB3 controller can be driven two ways:

* :class:`ToolDOGripper` — toggling UR tool digital output 0 (legacy ``SetIO(fun=1, pin=16)``).
  This is what URBackend has always done, but on a CB3 it only works when the OnRobot URCap is
  connected to the Compute Box and configured for digital-I/O control.
* :class:`OnRobotModbusGripper` — talking Modbus TCP directly to the OnRobot Compute Box
  (port 502, unit id 65). This works regardless of URCap wiring and is the fallback while the
  URCap↔box link is not set up in the lab.

Both implement the small :class:`Gripper` protocol so `URBackend` never has to know which one
it holds.
"""
from __future__ import annotations

import socket
import struct
import time
from abc import ABC, abstractmethod

from .base import RobotError


class Gripper(ABC):
    """Minimal actuator protocol: open/close plus best-effort status."""

    name: str = "abstract"

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def is_closed(self) -> bool | None:
        """Last commanded state, or None if never commanded / unknown."""

    @abstractmethod
    def grip_detected(self) -> bool | None:
        """True/False if the gripper reports it, None if the actuator can't tell."""


class ToolDOGripper(Gripper):
    """Drives the OnRobot through UR tool digital output 0.

    `io_getter` is a callable returning the *current* RTDE IO interface (rather than the
    interface itself) so a `URBackend` reconnect — which replaces `self.io` — keeps working
    without rebuilding the gripper.
    """

    name = "tool_do"

    def __init__(self, io_getter, do: int = 0, settle_s: float = 1.0, sleep=time.sleep):
        self._io_getter = io_getter
        self.do = int(do)
        self.settle_s = float(settle_s)
        self._sleep = sleep
        self._closed: bool | None = False

    def connect(self) -> None:
        pass   # the RTDE IO interface is owned and (re)connected by URBackend

    def disconnect(self) -> None:
        pass

    def _set(self, close: bool) -> None:
        io = self._io_getter()
        if not io.setToolDigitalOut(self.do, close):
            raise RobotError("gripper command refused")
        self._closed = close
        if self.settle_s:
            self._sleep(self.settle_s)

    def open(self) -> None:
        self._set(False)

    def close(self) -> None:
        self._set(True)

    def is_closed(self) -> bool | None:
        return self._closed

    def grip_detected(self) -> bool | None:
        return None   # tool DO carries no grip-detect feedback


class OnRobotModbusGripper(Gripper):
    """Minimal raw Modbus TCP client for the OnRobot Compute Box — no pymodbus dependency.

    Implements just what the RG2 v2 needs: function 0x03 (read holding registers) and 0x10
    (write multiple registers), over an MBAP-framed TCP connection to unit id 65.

    The register map below is transcribed from the OnRobot Compute Box Modbus manual and is
    NOT yet verified against the physical box in the lab — every address is a class constant
    (marked ``# verify on site``) so it can be corrected in one place once confirmed there.
    """

    name = "onrobot_modbus"

    DEFAULT_PORT = 502
    DEFAULT_UNIT_ID = 65

    # -- holding registers: write with function 0x10 (or 0x06 for a single register)
    REG_TARGET_FORCE = 0x0000   # 1/10 N                                   # verify on site
    REG_TARGET_WIDTH = 0x0001   # 1/10 mm                                  # verify on site
    REG_CONTROL = 0x0002        # bit0 grip, bit1 stop, bit3 grip w/offset # verify on site

    CONTROL_GRIP = 0x0001
    CONTROL_STOP = 0x0002
    CONTROL_GRIP_WITH_OFFSET = 0x0008

    # -- status/feedback registers: read with function 0x03
    REG_STATUS = 0x0100          # status bits, see STATUS_* below         # verify on site
    REG_ACTUAL_DEPTH = 0x0102                                            # verify on site
    REG_ACTUAL_REL_DEPTH = 0x0104                                        # verify on site
    REG_ACTUAL_WIDTH = 0x0107    # 1/10 mm                                 # verify on site

    STATUS_BUSY = 1 << 0
    STATUS_GRIP_DETECTED = 1 << 1
    STATUS_S1_PUSHED = 1 << 2
    STATUS_S1_TRIGGERED = 1 << 3
    STATUS_S2_PUSHED = 1 << 4
    STATUS_S2_TRIGGERED = 1 << 5
    STATUS_SAFETY_ERROR = 1 << 6

    WIDTH_MIN_MM, WIDTH_MAX_MM = 0.0, 110.0
    FORCE_MIN_N, FORCE_MAX_N = 3.0, 40.0

    POLL_S = 0.05

    def __init__(self, ip: str, port: int = DEFAULT_PORT, unit_id: int = DEFAULT_UNIT_ID,
                 force_n: float = 20.0, open_width_mm: float = 100.0, close_width_mm: float = 25.0,
                 settle_s: float = 1.0, timeout_s: float = 2.0, sleep=time.sleep,
                 sock_factory=socket.create_connection):
        self.ip = ip
        self.port = int(port)
        self.unit_id = int(unit_id)
        self.force_n = self._clamp(force_n, self.FORCE_MIN_N, self.FORCE_MAX_N)
        self.open_width_mm = self._clamp(open_width_mm, self.WIDTH_MIN_MM, self.WIDTH_MAX_MM)
        self.close_width_mm = self._clamp(close_width_mm, self.WIDTH_MIN_MM, self.WIDTH_MAX_MM)
        self.settle_s = float(settle_s)
        self.timeout_s = float(timeout_s)
        self._sleep = sleep
        self._sock_factory = sock_factory
        self._sock = None
        self._txid = 0
        self._closed: bool | None = None

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, float(value)))

    # -------------------------------------------------------------- connection
    def connect(self) -> None:
        try:
            self._sock = self._sock_factory((self.ip, self.port), timeout=self.timeout_s)
        except OSError as e:
            raise RobotError(
                f"cannot connect to OnRobot Compute Box at {self.ip}:{self.port}: {e}") from e

    def disconnect(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _ensure_connected(self):
        if self._sock is None:
            self.connect()
        return self._sock

    # ------------------------------------------------------------- raw Modbus
    def _next_txid(self) -> int:
        self._txid = (self._txid + 1) % 0x10000
        return self._txid

    def _recv_exact(self, sock, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise RobotError("OnRobot Modbus: connection closed by peer")
            buf += chunk
        return buf

    def _request(self, pdu: bytes) -> bytes:
        """Send one MBAP+PDU frame; return the response PDU (function code byte onward)."""
        sock = self._ensure_connected()
        txid = self._next_txid()
        header = struct.pack(">HHHB", txid, 0, len(pdu) + 1, self.unit_id)
        try:
            sock.sendall(header + pdu)
            resp_header = self._recv_exact(sock, 7)
            r_txid, _r_proto, r_len, r_unit = struct.unpack(">HHHB", resp_header)
            body = self._recv_exact(sock, r_len - 1)
        except RobotError:
            raise
        except (OSError, socket.timeout) as e:
            raise RobotError(f"OnRobot Modbus comms error: {e}") from e
        if r_txid != txid or r_unit != self.unit_id:
            raise RobotError("OnRobot Modbus: mismatched response header")
        func = body[0]
        if func & 0x80:
            exc_code = body[1] if len(body) > 1 else -1
            raise RobotError(
                f"OnRobot Modbus exception response (function {func & 0x7F:#04x}, code {exc_code})")
        return body

    def _read_holding(self, addr: int, count: int) -> list[int]:
        body = self._request(struct.pack(">BHH", 0x03, addr, count))
        byte_count = body[1]
        return list(struct.unpack(f">{byte_count // 2}H", body[2:2 + byte_count]))

    def _write_multiple(self, addr: int, values: list[int]) -> None:
        count = len(values)
        payload = struct.pack(">BHHB", 0x10, addr, count, count * 2)
        for v in values:
            payload += struct.pack(">H", v & 0xFFFF)
        self._request(payload)

    def _write_single(self, addr: int, value: int) -> None:
        self._request(struct.pack(">BHH", 0x06, addr, value & 0xFFFF))

    # ---------------------------------------------------------------- gripper
    def _command(self, width_mm: float) -> None:
        force10 = int(round(self.force_n * 10))
        width10 = int(round(width_mm * 10))
        self._write_multiple(self.REG_TARGET_FORCE, [force10, width10, self.CONTROL_GRIP])
        self._wait_not_busy()

    def _wait_not_busy(self) -> None:
        deadline = time.monotonic() + self.settle_s * 3
        while True:
            status = self._read_holding(self.REG_STATUS, 1)[0]
            if not (status & self.STATUS_BUSY):
                return
            if time.monotonic() >= deadline:
                raise RobotError("gripper timeout")
            self._sleep(self.POLL_S)

    def close(self) -> None:
        self._command(self.close_width_mm)
        self._closed = True

    def open(self) -> None:
        self._command(self.open_width_mm)
        self._closed = False

    def is_closed(self) -> bool | None:
        return self._closed

    def grip_detected(self) -> bool | None:
        status = self._read_holding(self.REG_STATUS, 1)[0]
        return bool(status & self.STATUS_GRIP_DETECTED)

    def status_registers(self) -> dict:
        """Raw status/width snapshot, for `gripper_test.py --modbus state`."""
        status = self._read_holding(self.REG_STATUS, 1)[0]
        width10 = self._read_holding(self.REG_ACTUAL_WIDTH, 1)[0]
        return {
            "status_bits": status,
            "busy": bool(status & self.STATUS_BUSY),
            "grip_detected": bool(status & self.STATUS_GRIP_DETECTED),
            "safety_error": bool(status & self.STATUS_SAFETY_ERROR),
            "actual_width_mm": width10 / 10.0,
        }
