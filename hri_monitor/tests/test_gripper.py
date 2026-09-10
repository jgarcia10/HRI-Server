"""Gripper actuators: ToolDOGripper (unchanged UR tool-DO behaviour, now factored out) and
OnRobotModbusGripper (new — a minimal raw Modbus TCP client for the OnRobot Compute Box,
exercised here against a fake socket that speaks just enough Modbus TCP to answer it)."""
import struct

import pytest

from hub.kit_study.robotd.base import RobotError
from hub.kit_study.robotd.gripper import OnRobotModbusGripper, ToolDOGripper
from hub.kit_study.robotd.ur import URBackend
from tests.test_robotd_ur import CAL, FakeControl, FakeIO, FakeReceive, FakeRobot


# ------------------------------------------------------------------- fake Modbus TCP socket
class FakeModbusSocket:
    """Just enough server-side Modbus TCP (MBAP + function 0x03/0x10/0x06) to answer
    OnRobotModbusGripper. `busy_reads` scripts how many status reads report bit0 (busy) before
    it clears; `exception_on` maps a function code to a Modbus exception code to return
    instead of a normal response."""

    def __init__(self, unit_id=65, busy_reads=0, status_extra_bits=0, exception_on=None,
                 raise_on_recv=None):
        self.unit_id = unit_id
        self.busy_reads = busy_reads
        self.status_extra_bits = status_extra_bits
        self.exception_on = exception_on or {}
        self.raise_on_recv = raise_on_recv
        self._status_reads = 0
        self._out = b""
        self.writes = []          # [(addr, [values...]), ...]
        self.singles = []         # [(addr, value), ...]
        self.reads = []           # [(addr, count), ...]
        self.closed = False

    def settimeout(self, t):
        pass

    def close(self):
        self.closed = True

    def sendall(self, data: bytes) -> None:
        self._handle(data)

    def recv(self, n: int) -> bytes:
        if self.raise_on_recv is not None:
            raise self.raise_on_recv
        chunk, self._out = self._out[:n], self._out[n:]
        return chunk

    # -------------------------------------------------------------- request handling
    def _reply(self, txid: int, unit: int, body: bytes) -> None:
        header = struct.pack(">HHHB", txid, 0, len(body) + 1, unit)
        self._out += header + body

    def _exception(self, txid: int, unit: int, func: int, code: int) -> None:
        self._reply(txid, unit, struct.pack(">BB", func | 0x80, code))

    def _handle(self, data: bytes) -> None:
        txid, _proto, length, unit = struct.unpack(">HHHB", data[:7])
        pdu = data[7:7 + length - 1]
        func = pdu[0]
        if func in self.exception_on:
            self._exception(txid, unit, func, self.exception_on[func])
            return
        if func == 0x03:
            addr, count = struct.unpack(">HH", pdu[1:5])
            self.reads.append((addr, count))
            values = self._read_values(addr, count)
            body = struct.pack(">BB", 0x03, count * 2)
            for v in values:
                body += struct.pack(">H", v)
            self._reply(txid, unit, body)
        elif func == 0x10:
            addr, count, byte_count = struct.unpack(">HHB", pdu[1:6])
            values = list(struct.unpack(f">{count}H", pdu[6:6 + byte_count]))
            self.writes.append((addr, values))
            self._reply(txid, unit, struct.pack(">BHH", 0x10, addr, count))
        elif func == 0x06:
            addr, value = struct.unpack(">HH", pdu[1:5])
            self.singles.append((addr, value))
            self._reply(txid, unit, struct.pack(">BHH", 0x06, addr, value))
        else:
            self._exception(txid, unit, func, 1)   # illegal function

    def _read_values(self, addr: int, count: int) -> list:
        if addr == OnRobotModbusGripper.REG_STATUS:
            busy = self._status_reads < self.busy_reads
            self._status_reads += 1
            bits = self.status_extra_bits | (OnRobotModbusGripper.STATUS_BUSY if busy else 0)
            return [bits]
        if addr == OnRobotModbusGripper.REG_ACTUAL_WIDTH:
            return [250]
        return [0] * count


def make_gripper(sock=None, busy_reads=0, status_extra_bits=0, exception_on=None,
                  raise_on_recv=None, **gripper_kw):
    if sock is None:
        sock = FakeModbusSocket(busy_reads=busy_reads, status_extra_bits=status_extra_bits,
                                exception_on=exception_on, raise_on_recv=raise_on_recv)
    gripper_kw.setdefault("sleep", lambda s: None)
    g = OnRobotModbusGripper("10.0.0.5", sock_factory=lambda addr, timeout=None: sock,
                             **gripper_kw)
    return g, sock


# --------------------------------------------------------------------------- close / open
def test_close_writes_scaled_registers_and_waits_for_not_busy():
    g, sock = make_gripper(force_n=15.0, close_width_mm=30.0, busy_reads=2)
    g.close()
    assert sock.writes == [(OnRobotModbusGripper.REG_TARGET_FORCE, [150, 300, 1])]
    assert sock.reads.count((OnRobotModbusGripper.REG_STATUS, 1)) == 3   # busy, busy, idle
    assert g.is_closed() is True


def test_open_writes_scaled_registers_and_waits_for_not_busy():
    g, sock = make_gripper(open_width_mm=90.0, force_n=10.0, busy_reads=0)
    g.open()
    assert sock.writes == [(OnRobotModbusGripper.REG_TARGET_FORCE, [100, 900, 1])]
    assert g.is_closed() is False


def test_grip_detected_reads_status_bit1():
    g, sock = make_gripper(status_extra_bits=OnRobotModbusGripper.STATUS_GRIP_DETECTED)
    assert g.grip_detected() is True
    sock2 = FakeModbusSocket()
    g2, _ = make_gripper(sock=sock2)
    assert g2.grip_detected() is False


# ------------------------------------------------------------------------------- failures
def test_timeout_when_status_never_clears_busy_raises_robot_error():
    g, sock = make_gripper(busy_reads=10_000, settle_s=0.01)   # never goes idle in time
    with pytest.raises(RobotError, match="gripper timeout"):
        g.close()


def test_modbus_exception_response_raises_robot_error():
    sock = FakeModbusSocket(exception_on={0x10: 4})   # server device failure on write
    g, _ = make_gripper(sock=sock)
    with pytest.raises(RobotError, match="exception"):
        g.close()


def test_socket_error_on_connect_raises_robot_error():
    def boom(addr, timeout=None):
        raise OSError("connection refused")
    g = OnRobotModbusGripper("10.0.0.5", sock_factory=boom, sleep=lambda s: None)
    with pytest.raises(RobotError, match="cannot connect"):
        g.connect()


def test_recv_error_raises_robot_error():
    sock = FakeModbusSocket(raise_on_recv=OSError("reset by peer"))
    g, _ = make_gripper(sock=sock)
    with pytest.raises(RobotError, match="comms error"):
        g.close()


# ---------------------------------------------------------------------------------- clamps
def test_force_and_width_are_clamped_to_valid_ranges():
    g, _ = make_gripper(force_n=100.0, open_width_mm=500.0, close_width_mm=-10.0)
    assert g.force_n == OnRobotModbusGripper.FORCE_MAX_N
    assert g.open_width_mm == OnRobotModbusGripper.WIDTH_MAX_MM
    assert g.close_width_mm == OnRobotModbusGripper.WIDTH_MIN_MM

    g2, _ = make_gripper(force_n=0.5)
    assert g2.force_n == OnRobotModbusGripper.FORCE_MIN_N


# ---------------------------------------------------------------------------- ToolDOGripper
def test_tool_do_gripper_close_and_open():
    io = FakeIO()
    g = ToolDOGripper(io_getter=lambda: io, do=0, settle_s=0.0)
    g.close()
    assert io.calls == [(0, True)]
    assert g.is_closed() is True
    g.open()
    assert io.calls == [(0, True), (0, False)]
    assert g.is_closed() is False
    assert g.grip_detected() is None


def test_tool_do_gripper_false_return_raises_robot_error():
    io = FakeIO()
    io.setToolDigitalOut = lambda out_id, level: False
    g = ToolDOGripper(io_getter=lambda: io, do=0, settle_s=0.0)
    with pytest.raises(RobotError, match="gripper command refused"):
        g.close()
    assert g.is_closed() is False   # unchanged on failure


# ------------------------------------------------------------------ URBackend + fake gripper
class FakeGripper:
    name = "fake"

    def __init__(self):
        self.calls = []
        self._closed = False
        self.connected = False

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def close(self):
        self.calls.append("close")
        self._closed = True

    def open(self):
        self.calls.append("open")
        self._closed = False

    def is_closed(self):
        return self._closed

    def grip_detected(self):
        return None


def make_backend_with_fake_gripper():
    robot = FakeRobot()
    c, r, io = FakeControl(robot), FakeReceive(robot), FakeIO()
    fg = FakeGripper()
    b = URBackend("192.168.131.140", CAL, rtde_factory=lambda ip: (c, r, io), gripper=fg,
                  gripper_settle_s=0.0, poll_s=0.0)
    b.connect()
    return b, fg


def test_urbackend_pick_uses_gripper_close():
    b, fg = make_backend_with_fake_gripper()
    b.pick("RD1")
    assert fg.calls == ["close"]
    assert b.state().gripper_closed is True


def test_urbackend_place_and_open_gripper_use_gripper_open():
    b, fg = make_backend_with_fake_gripper()
    b.place("L")
    assert fg.calls == ["open"]
    assert b.state().gripper_closed is False
    fg.calls.clear()
    fg._closed = True
    b.open_gripper()
    assert fg.calls == ["open"]
    assert b.state().gripper_closed is False


def test_urbackend_connect_and_disconnect_delegate_to_gripper():
    b, fg = make_backend_with_fake_gripper()
    assert fg.connected is True
    b.disconnect()
    assert fg.connected is False
