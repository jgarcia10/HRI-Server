"""Gripper actuators for the UR backend.

The OnRobot RG2 v2 on the study's CB3 controller can be driven several ways:

* :class:`DualDOGripper` — the lab's actual wiring, measured on site 2026-09-10/11: two tool
  digital outputs are the two directions of an H-bridge internal to the gripper (DO0 = close,
  DO1 = open), (1, 1) latches a gripper fault, (0, 0) is neutral. This is what `robot.yaml`
  ships and what `URBackend` uses by default.
* :class:`ToolDOGripper` — a single tool digital output, legacy ``SetIO(fun=1, pin=16)``
  wiring/URCap behaviour (one line, polarity selects open/close). Kept for the URCap-managed
  digital-I/O mode and for `ursim.yaml`.
* :class:`OnRobotModbusGripper` — talking Modbus TCP directly to the OnRobot Compute Box
  (port 502, unit id 65). This works regardless of URCap wiring and is the fallback while the
  URCap↔box link is not set up in the lab.
* :class:`OnRobotURCapGripper` — driving the OnRobot unified URCap's `rg_grip(...)` through a
  one-shot URScript program sent to the controller. This is the only way to actuate the gripper
  once the URCap is (re)installed: the URCap daemon only answers XML-RPC calls from URScript
  running *on the controller*, so nothing on the network can reach it directly.

All four implement the small :class:`Gripper` protocol so `URBackend` never has to know which
one it holds.
"""
from __future__ import annotations

import socket
import struct
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path

from .base import RobotError

# -- UR primary/secondary interface framing, used by OnRobotURCapGripper -------------------
UR_PRIMARY_PORT = 30001      # streams RobotState + RobotMessage packets once connected
UR_SECONDARY_PORT = 30002    # accepts one URScript program per connection ("play" equivalent)
ROBOT_MESSAGE_TYPE = 20      # UR real-time client interface: message type 20 == ROBOT_MESSAGE

_HEADER_FMT = ">IB"                             # packet length (incl. header), message type
_HEADER_LEN = struct.calcsize(_HEADER_FMT)      # 5
_BODY_PREFIX_FMT = ">QBB"                       # timestamp, source, robotMessageType
_BODY_PREFIX_LEN = struct.calcsize(_BODY_PREFIX_FMT)   # 10


def encode_robot_message(text: str, subtype: int = 0) -> bytes:
    """Build one RobotMessage (type 20) primary-interface packet carrying `text`.

    Real RobotMessage payloads vary by `robotMessageType` (POPUP, TEXT_MSG, PROGRAM label,
    …); `OnRobotURCapGripper` only cares about the printable ASCII text past the fixed
    timestamp/source/robotMessageType prefix, so this stub zeroes the timestamp/source and
    puts `subtype` in the robotMessageType byte. Exercised by `tests/test_gripper.py` to
    script the fake controller's primary-interface stream.
    """
    payload = text.encode("ascii", errors="replace")
    body = struct.pack(_BODY_PREFIX_FMT, 0, 0, subtype) + payload
    return struct.pack(_HEADER_FMT, _HEADER_LEN + len(body), ROBOT_MESSAGE_TYPE) + body


def _extract_robot_message_text(packet: bytes) -> str | None:
    """Printable ASCII text from one already-framed RobotMessage packet, or None."""
    payload = packet[_HEADER_LEN + _BODY_PREFIX_LEN:]
    text = "".join(chr(b) for b in payload if 32 <= b < 127)
    return text or None


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
    """Drives the OnRobot RG2 v2 through a single UR tool digital output — the lab's actual
    wiring, measured on site 2026-09-11: a level-driven gripper, not an edge/pulse one.

    * `do` (tool DO0 by default) is the only control line: driving it high commands CLOSED,
      low commands OPEN (polarity selected by `close_high`), and the gripper travels
      continuously while the level is held — full stroke takes ~7 s. Resting at the OPEN
      level is the safe idle state.
    * `other_do` (tool DO1 by default) must NEVER be written during normal operation —
      asserting it is what latched a gripper fault for an entire day of testing
      (2026-09-10). The only exception is `connect()`, which forces it low *once* so a stale
      DO1 (or a leftover close level) can never survive a reconnect, then commands the
      gripper open. Set `other_do=None` to skip this (e.g. a rig where DO1 is wired to
      something else entirely).
    * Closing fully on air (nothing between the fingers) presses the fingertip safety
      switches and latches a fault; closing onto a part is fine. Recovery is the documented
      tool-voltage power cycle plus a wake pulse — see `URBackend.reset_gripper`.

    `io_getter` is a callable returning the *current* RTDE IO interface (rather than the
    interface itself) so a `URBackend` reconnect — which replaces `self.io` — keeps working
    without rebuilding the gripper.
    """

    name = "tool_do"

    def __init__(self, io_getter, do: int = 0, settle_s: float = 1.0, sleep=time.sleep,
                 close_high: bool = True, other_do: int | None = 1):
        self._io_getter = io_getter
        self.do = int(do)
        self.other_do = None if other_do is None else int(other_do)
        self.settle_s = float(settle_s)
        self._sleep = sleep
        # Lab RG2 v2, measured 2026-09-11: DO0 = 1 closes, DO0 = 0 opens → close_high=True.
        self.close_high = bool(close_high)
        self._closed: bool | None = False

    def connect(self) -> None:
        """A reconnect must never inherit a stale DO1 or a leftover close level: force the
        other line low once (best-effort — a refusal here must not block connecting) and
        then command the gripper open."""
        if self.other_do is not None:
            io = self._io_getter()
            try:
                io.setToolDigitalOut(self.other_do, False)
            except Exception:
                pass   # best-effort: DO1 must never be asserted, but a failed clear here
                       # must not stop the reconnect from completing
        self._set(False)

    def disconnect(self) -> None:
        pass

    def _set(self, close: bool) -> None:
        io = self._io_getter()
        level = close if self.close_high else (not close)
        if not io.setToolDigitalOut(self.do, level):
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


class DualDOGripper(Gripper):
    """Drives an OnRobot RG2 v2 as a two-line digital gripper on the UR tool connector.

    *** DO NOT USE THIS ON THE LAB ROBOT. *** Re-measured 2026-09-11: the lab's RG2 v2 is a
    single-line, level-driven gripper (tool DO0 only — see `ToolDOGripper`). Tool DO1 must
    NEVER be written on this robot; asserting it (as `open_do` does here) is exactly what
    latched a gripper fault for a full day of testing on 2026-09-10. `robot.yaml` must never
    set `gripper.kind: dual_do`. This class is kept only for a *differently* wired RG2 v2 —
    one where DO0/DO1 genuinely are the two directions of an internal H-bridge — should that
    ever show up on a different robot; it is exercised below purely so that wiring stays
    correct in case it is ever needed again.

    Measured on site 2026-09-10 (superseded by the single-line finding above) with the tool
    output "controlled by user", 24 V: DO0 closes, DO1 opens — the two directions of an
    H-bridge *inside* the gripper, as that day's wiring appeared to behave. (0, 0) is neutral
    (the gripper holds position, nothing moves); (1, 1) is FORBIDDEN — it latches a gripper
    fault that survives a power cycle (recovered only by a full controller reboot that day).

    Every direction change is therefore break-before-make: drop the line that must not be high
    first, wait `BREAK_GAP_S`, then raise the line that must be high — so the forbidden (1, 1)
    state is structurally impossible to reach, even transiently, no matter what order `close()`/
    `open()`/`connect()`/`disconnect()` are called in. `connect()`/`disconnect()` always leave
    both lines low, so a reconnect or a controller reboot never leaves a direction asserted.

    `io_getter` follows the `ToolDOGripper` pattern: a callable returning the *current* RTDE IO
    interface (not the interface itself), so a `URBackend` reconnect — which replaces `self.io`
    — keeps working without rebuilding the gripper. `recv_getter`, if given, is a callable
    returning the RTDE *receive* interface, used only by `status()`.
    """

    name = "dual_do"

    BREAK_GAP_S = 0.15    # dwell between dropping the unwanted line and raising the wanted one
    FAULT_AI1_V = 5.0     # measured: AI1 ~1.35 V ready, ~3.4 V moving, ~6.4 V FAULT

    # ur_rtde 1.6.5's RTDEReceiveInterface has no tool-analog getter at all (only
    # getStandardAnalogInput0/1, which read the *controller's* standard AI, not the tool
    # connector's AI0/AI1 the measured ready/moving/fault signatures are about) — these tuples
    # are here so status() picks one up automatically the day a build exposes it, without code
    # changes; until then `_pick(recv, ...)` finds nothing and status() returns None.
    _AI1_GETTERS = ("getToolAnalogInput1", "getActualToolAnalogInput1")
    _CURRENT_GETTERS = ("getToolCurrent", "getActualToolCurrent")

    def __init__(self, io_getter, close_do: int = 0, open_do: int = 1, settle_s: float = 1.0,
                 hold_close: bool = True, sleep=time.sleep, recv_getter=None):
        if int(close_do) == int(open_do):
            raise RobotError("DualDOGripper: close_do and open_do must be different lines")
        self._io_getter = io_getter
        self._recv_getter = recv_getter
        self.close_do = int(close_do)
        self.open_do = int(open_do)
        self.settle_s = float(settle_s)
        self.hold_close = bool(hold_close)
        self._sleep = sleep
        self._closed: bool | None = None

    # --------------------------------------------------------- low-level: break-before-make
    def _write(self, do: int, level: bool) -> None:
        io = self._io_getter()
        if not io.setToolDigitalOut(do, level):
            raise RobotError("gripper command refused")

    def _drive(self, direction: str | None) -> None:
        """Move to `direction` ("close" | "open" | None == neutral).

        Structurally cannot assert both lines high, even transiently: it always writes every
        line that must end up low *first*, waits `BREAK_GAP_S`, and only then writes the (at
        most one) line that must end up high.
        """
        want_close = direction == "close"
        want_open = direction == "open"
        if want_close and want_open:
            raise RobotError("DualDOGripper: close and open requested at once")   # unreachable
        # Break: drop whichever line(s) must not be high.
        if not want_close:
            self._write(self.close_do, False)
        if not want_open:
            self._write(self.open_do, False)
        self._sleep(self.BREAK_GAP_S)
        # Make: raise the one line that was requested, if any.
        if want_close:
            self._write(self.close_do, True)
        if want_open:
            self._write(self.open_do, True)

    def _neutral(self) -> None:
        self._drive(None)

    # -------------------------------------------------------------------------- lifecycle
    def connect(self) -> None:
        self._neutral()   # a reconnect (or a controller reboot) must never inherit an asserted line

    def disconnect(self) -> None:
        try:
            self._neutral()
        except (RobotError, OSError):
            pass   # best-effort: disconnect must not raise

    # -------------------------------------------------------------------------- actuator
    def close(self) -> None:
        self._drive("close")
        if self.settle_s:
            self._sleep(self.settle_s)
        if self.hold_close:
            pass   # keep the close line asserted — the grip must hold while the arm carries the part
        else:
            self._neutral()
        self._closed = True

    def open(self) -> None:
        self._drive("open")
        if self.settle_s:
            self._sleep(self.settle_s)
        self._neutral()   # never hold against the open end stop
        self._closed = False

    def is_closed(self) -> bool | None:
        return self._closed

    def grip_detected(self) -> bool | None:
        return None   # no grip-detect feedback on a two-line digital gripper

    # ---------------------------------------------------------------------------- feedback
    @staticmethod
    def _pick(obj, names):
        return next((getattr(obj, n) for n in names if hasattr(obj, n)), None)

    def status(self) -> dict | None:
        """{"ai1": V, "current": A, "fault": AI1 > FAULT_AI1_V}, or None if `recv_getter` was
        not given, or if this ur_rtde build exposes no tool-analog getter (see `_AI1_GETTERS`).
        Never raises for a missing getter — the class does not depend on this working."""
        if self._recv_getter is None:
            return None
        recv = self._recv_getter()
        ai1_getter = self._pick(recv, self._AI1_GETTERS)
        if ai1_getter is None:
            return None
        ai1 = float(ai1_getter())
        current_getter = self._pick(recv, self._CURRENT_GETTERS)
        current = float(current_getter()) if current_getter is not None else None
        return {"ai1": ai1, "current": current, "fault": ai1 > self.FAULT_AI1_V}


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


class OnRobotURCapGripper(Gripper):
    """Drives the OnRobot RG2 v2 through the OnRobot unified URCap on a CB3 controller.

    The URCap daemon lives inside the controller and answers only to URScript's `rg_grip(...)`
    (XML-RPC to localhost) — nothing on the network can reach it directly. So each open/close:

    1. builds a one-shot program from the URCap-generated template (`script_path`), substituting
       the requested width/force into its `rg_grip(...)` call;
    2. watches the *primary* interface (port 30001) for the RobotMessage stream in a background
       thread: our own `textmsg` markers, the controller's own PROGRAM_*_STARTED/STOPPED
       messages, and any popup/error text (e.g. "Missing URCap", "No RG gripper connected");
    3. sends the program once over the *secondary* interface (port 30002) — a single `sendall`
       then close, exactly as PolyScope's "play" button does;
    4. always restores the ur_rtde control script afterwards via `reupload()`, because loading
       any other program onto the controller kills it — on success or on failure alike.

    `sock_factory(addr, timeout=...)` and `sleep(seconds)` are injectable so tests can script the
    primary-interface stream and the secondary-interface send without touching a real socket.
    """

    name = "onrobot_urcap"

    DEFAULT_SCRIPT_PATH = Path(__file__).parent / "onrobot" / "rg_grip_urcap_5.15.0.script"
    WHILE_MARKER = "  while (True):\n"       # everything before this line is the URCap preamble
    DONE_MARKER = "KIT rg_grip done"
    FAILURE_MARKERS = ("halted", "No RG gripper", "Missing", "error")
    LISTEN_POLL_S = 0.2
    REUPLOAD_SETTLE_S = 0.2                   # let the controller drop the temp program first

    PRIMARY_PORT = UR_PRIMARY_PORT
    SECONDARY_PORT = UR_SECONDARY_PORT

    def __init__(self, ip: str, script_path=None, force_n: float = 20.0,
                 open_width_mm: float = 100.0, close_width_mm: float = 20.0,
                 timeout_s: float = 15.0, reupload=None,
                 sock_factory=socket.create_connection, sleep=time.sleep):
        self.ip = ip
        self.script_path = Path(script_path) if script_path else self.DEFAULT_SCRIPT_PATH
        self.force_n = float(force_n)
        self.open_width_mm = float(open_width_mm)
        self.close_width_mm = float(close_width_mm)
        self.timeout_s = float(timeout_s)
        self.reupload = reupload
        self._sock_factory = sock_factory
        self._sleep = sleep
        self._preamble = self._load_preamble(self.script_path)
        self._closed: bool | None = None
        self.last_messages: list[str] = []   # captured RobotMessage text from the last open/close

    @classmethod
    def _load_preamble(cls, path) -> str:
        """Everything up to (not including) the top-level ``  while (True):`` line.

        Searched with a leading ``\\n`` so it only matches that line at *exactly* 2-space
        indent — the template also nests a differently-indented ``while (True):`` inside its
        step-counter thread, and a bare substring search matches inside that deeper indent too
        (2 of its 4 leading spaces line up with the marker).
        """
        text = Path(path).read_text()
        anchored = "\n" + cls.WHILE_MARKER
        idx = text.find(anchored)
        if idx == -1:
            raise RobotError(
                f"URCap template {path} is missing the {cls.WHILE_MARKER.strip()!r} marker")
        return text[:idx + 1]

    def _render_program(self, width_mm: float, force_n: float) -> str:
        return (
            self._preamble
            + '  textmsg("KIT rg_grip start")\n'
            + f'  on_return = rg_grip({width_mm:.1f}, {force_n:.1f}, tool_index = 0, '
              'blocking = True, depth_comp = False, popupmsg = True)\n'
            + '  textmsg("KIT rg_grip done")\n'
            + '  sleep(0.3)\n'
            + 'end\n'
        )

    # -------------------------------------------------------------- lifecycle
    def connect(self) -> None:
        pass   # nothing to open ahead of time — each open()/close() connects for itself

    def disconnect(self) -> None:
        pass

    # ---------------------------------------------------------------- actuator
    def open(self) -> None:
        self._actuate(self.open_width_mm, closed=False)

    def close(self) -> None:
        self._actuate(self.close_width_mm, closed=True)

    def is_closed(self) -> bool | None:
        return self._closed

    def grip_detected(self) -> bool | None:
        return None   # could be parsed from the URCap's rg_Grip_detected chatter later

    # ------------------------------------------------------------------- wire
    def _actuate(self, width_mm: float, closed: bool) -> None:
        program = self._render_program(width_mm, self.force_n)
        lock = threading.Lock()
        outcome: dict = {"result": None, "text": None}
        done_event = threading.Event()
        messages: list[str] = []

        def record(text: str) -> None:
            messages.append(text)
            with lock:
                if outcome["result"] is not None:
                    return
                if self.DONE_MARKER in text:
                    outcome["result"] = "success"
                elif any(marker in text for marker in self.FAILURE_MARKERS):
                    outcome["result"] = "failure"
                    outcome["text"] = text
                elif "STOPPED" in text:
                    outcome["result"] = "failure"
                    outcome["text"] = text
                else:
                    return
            done_event.set()

        stop_listen = threading.Event()
        listener = threading.Thread(target=self._listen_primary, args=(record, stop_listen),
                                     daemon=True)
        listener.start()
        try:
            self._send_program(program)
            if not done_event.wait(self.timeout_s):
                raise RobotError("gripper program timeout")
        finally:
            stop_listen.set()
            listener.join(timeout=self.timeout_s)
            if self.reupload is not None:
                self._sleep(self.REUPLOAD_SETTLE_S)
                self.reupload()
        self.last_messages = messages
        if outcome["result"] == "failure":
            raise RobotError(f"gripper program failed: {outcome['text']}")
        self._closed = closed

    def _send_program(self, program: str) -> None:
        try:
            sock = self._sock_factory((self.ip, self.SECONDARY_PORT), timeout=self.timeout_s)
        except OSError as e:
            raise RobotError(
                f"cannot connect to UR secondary interface at {self.ip}:{self.SECONDARY_PORT}: "
                f"{e}") from e
        try:
            sock.sendall(program.encode("utf-8"))
        except OSError as e:
            raise RobotError(f"failed to send gripper program: {e}") from e
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _listen_primary(self, on_message, stop_event: threading.Event) -> None:
        try:
            sock = self._sock_factory((self.ip, self.PRIMARY_PORT), timeout=self.timeout_s)
        except OSError:
            return   # the secondary-interface send (or the timeout) still governs the outcome
        buf = b""
        try:
            while not stop_event.is_set():
                try:
                    sock.settimeout(self.LISTEN_POLL_S)
                    chunk = sock.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                buf = self._consume_packets(buf, on_message)
        finally:
            try:
                sock.close()
            except OSError:
                pass

    @staticmethod
    def _consume_packets(buf: bytes, on_message) -> bytes:
        while len(buf) >= _HEADER_LEN:
            length, mtype = struct.unpack_from(_HEADER_FMT, buf, 0)
            if length < _HEADER_LEN:
                buf = buf[1:]          # malformed framing: resync one byte at a time
                continue
            if len(buf) < length:
                break                  # wait for the rest of this packet
            packet, buf = buf[:length], buf[length:]
            if mtype == ROBOT_MESSAGE_TYPE:
                text = _extract_robot_message_text(packet)
                if text:
                    on_message(text)
        return buf
