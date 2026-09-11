#!/usr/bin/env python3
"""Actuate the OnRobot RG2 v2 through the lab's actual wiring — two tool digital outputs as the
two directions of an H-bridge (DO0 = close, DO1 = open), driven the same way the app does
(`hub.kit_study.robotd.gripper.DualDOGripper`). Prints the tool current and AI1 before/after
each command so the operator can read ready/moving/fault straight off the terminal:

    .venv/bin/python tools/gripper_test.py open          # break-before-make: DO0=0, gap, DO1=1, then neutral
    .venv/bin/python tools/gripper_test.py close         # break-before-make: DO1=0, gap, DO0=1, held
    .venv/bin/python tools/gripper_test.py cycle         # open, close, open
    .venv/bin/python tools/gripper_test.py state         # tool current/AI1/AI0 snapshot, no actuation

Measured signatures (24 V tool output): AI1 ~1.35 V = ready, ~3.4 V = moving, ~6.4 V = FAULT;
current ~85 mA idle, ~126-148 mA moving, drops to ~63-69 mA in the fault state. (1, 1) — both
lines high at once — is FORBIDDEN: it latches a gripper fault that survives a power cycle, which
is exactly why this tool (like `DualDOGripper` itself) never writes both lines without dropping
the unwanted one first. If the gripper ever reports FAULT, see RUNBOOK_robot.md §C.3 for recovery
(`tools/gripper_check.py --matrix` is the decisive check afterwards).

`--modbus IP` drives the OnRobot Compute Box directly over Modbus TCP (port 502, unit id 65),
bypassing the UR tool connector entirely — use this to check a box from the laptop without going
through the app:

    .venv/bin/python tools/gripper_test.py open  --modbus 192.168.1.1
    .venv/bin/python tools/gripper_test.py close --modbus 192.168.1.1
    .venv/bin/python tools/gripper_test.py cycle --modbus 192.168.1.1
    .venv/bin/python tools/gripper_test.py state --modbus 192.168.1.1   # raw status/width regs

`--urcap [IP]` drives the OnRobot unified URCap's rg_grip(...) the way the app would if the
URCap were installed and connected: sends a one-shot URScript program over the UR's secondary
interface (30002) and watches the primary interface (30001) for completion. Prints every
RobotMessage text it captured, so a "Missing URCap" / "No RG gripper connected" popup on the
pendant shows up here too:

    .venv/bin/python tools/gripper_test.py open  --urcap
    .venv/bin/python tools/gripper_test.py close --urcap
    .venv/bin/python tools/gripper_test.py cycle --urcap
    .venv/bin/python tools/gripper_test.py open  --urcap 147.250.35.40   # explicit robot IP

DEPRECATED: `--close-low` (the old single-tool-DO wiring) is no longer the default — the lab
gripper is wired as two lines, not one. If you specifically need the legacy single-line path
(e.g. a different gripper on a different DO layout), pass `--single-do` explicitly:

    .venv/bin/python tools/gripper_test.py cycle --single-do                # DO0: 0=open, 1=close
    .venv/bin/python tools/gripper_test.py cycle --single-do --close-low    # DO0: 1=open, 0=close
"""
import socket
import struct
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hub.kit_study.robotd.gripper import (DualDOGripper, OnRobotModbusGripper,  # noqa: E402
                                          OnRobotURCapGripper)
from hub.kit_study.robotd.ur import GRIPPER_TOOL_DO  # noqa: E402

IP = "147.250.35.40"


# ------------------------------------------------------------------------ tool feedback stream
class ToolStream(threading.Thread):
    """Keeps the secondary interface (port 30002) open and exposes the latest ToolData sample
    (~10 Hz): tool voltage/current and analog inputs AI0/AI1. `rtde_receive.RTDEReceiveInterface`
    exposes no tool-analog getter on this ur_rtde build (see `DualDOGripper.status` — it
    returns None here for exactly that reason), so this raw parse is how the operator actually
    sees ready/moving/fault. Same wire format `tools/gripper_check.py` already relies on."""

    def __init__(self, ip: str):
        super().__init__(daemon=True)
        self.ip = ip
        self.latest = None
        self.stop = threading.Event()

    def run(self) -> None:
        s = socket.create_connection((self.ip, 30002), timeout=3)
        buf = b""
        try:
            while not self.stop.is_set():
                try:
                    buf += s.recv(65536)
                except socket.timeout:
                    continue
                while len(buf) >= 5:
                    size, mtype = struct.unpack(">IB", buf[:5])
                    if size < 5 or len(buf) < size:
                        break
                    msg, buf = buf[5:size], buf[size:]
                    if mtype != 16:   # 16 == TOOL_DATA package in the secondary-interface stream
                        continue
                    i = 0
                    while i + 5 <= len(msg):
                        psize, ptype = struct.unpack(">IB", msg[i:i + 5])
                        body = msg[i + 5:i + psize]
                        if ptype == 2 and len(body) >= 32:
                            f = struct.unpack(">BBddfBffB", body[:32])
                            self.latest = {"ai0": f[2], "ai1": f[3], "volt": f[5], "cur": f[6]}
                        i += psize
        finally:
            s.close()


def _ai1_label(ai1) -> str:
    if ai1 is None:
        return "?"
    if ai1 > DualDOGripper.FAULT_AI1_V:
        return "FAULT"
    if ai1 > 2.0:
        return "moving"
    return "ready"


# ----------------------------------------------------------------------------------- dual_do
def _run_dual_do(cmd: str, ip: str) -> int:
    import rtde_io, rtde_receive
    io = rtde_io.RTDEIOInterface(ip)
    recv = rtde_receive.RTDEReceiveInterface(ip)
    stream = ToolStream(ip)
    stream.start()
    time.sleep(1.0)
    g = DualDOGripper(io_getter=lambda: io, recv_getter=lambda: recv, sleep=time.sleep)

    def snapshot(label: str) -> None:
        td = stream.latest
        if td is None:
            print(f"  {label}: no tool data yet")
            return
        print(f"  {label:<13} current {td['cur'] * 1000:5.0f} mA   AI1 {td['ai1']:5.2f} V "
              f"({_ai1_label(td['ai1'])})   AI0 {td['ai0']:5.2f} V")

    def act(name: str, fn) -> None:
        snapshot(f"{name} before")
        fn()
        snapshot(f"{name} after")
        print(f"    is_closed() -> {g.is_closed()}   status() -> {g.status()}")

    print(f"gripper via dual tool DO on {ip}: DO{g.close_do}=close, DO{g.open_do}=open "
          "(break-before-make, (1,1) never written)")
    try:
        if cmd == "open":
            act("open", g.open)
        elif cmd == "close":
            act("close", g.close)
        elif cmd == "cycle":
            act("open", g.open)
            act("close", g.close)
            act("open", g.open)
        elif cmd == "state":
            snapshot("state")
    finally:
        g.disconnect()   # forces neutral, best-effort — never leaves a direction asserted
        stream.stop.set()
        recv.disconnect()
        io.disconnect()
    return 0


# --------------------------------------------------------------------------- legacy single_do
def _run_tool_do(cmd: str, ip: str, close_high: bool = True) -> int:
    """DEPRECATED path for a single tool-DO gripper (`--single-do`). close_high=False -> DO0=0
    closes, DO0=1 opens; the lab RG2 v2 is no longer wired this way (see module docstring)."""
    import rtde_io, rtde_receive
    io = rtde_io.RTDEIOInterface(ip)
    recv = rtde_receive.RTDEReceiveInterface(ip)
    def do0():
        bits = int(recv.getActualDigitalOutputBits())
        return bool(bits >> (16 + GRIPPER_TOOL_DO) & 1)      # tool DOs are bits 16-17
    def set_(close: bool):
        level = close if close_high else (not close)
        ok = io.setToolDigitalOut(GRIPPER_TOOL_DO, level)
        time.sleep(1.5)
        print(f"  {'close' if close else 'open '} -> setToolDigitalOut({GRIPPER_TOOL_DO}, {level}) -> {ok}; DO0 reads {do0()}")
    print(f"[DEPRECATED single-line path] gripper via tool DO{GRIPPER_TOOL_DO} on {ip}; DO0 currently {do0()}")
    if cmd == "open":
        set_(False)
    elif cmd == "close":
        set_(True)
    elif cmd == "cycle":
        set_(False); set_(True); set_(False)
    elif cmd == "state":
        pass   # do0() already printed above
    recv.disconnect(); io.disconnect()
    return 0


def _run_modbus(cmd: str, ip: str) -> int:
    g = OnRobotModbusGripper(ip)
    g.connect()
    print(f"gripper via OnRobot Compute Box Modbus TCP on {ip}:{g.port} (unit {g.unit_id})")
    try:
        if cmd == "open":
            g.open(); print(f"  open -> width {g.open_width_mm} mm; {g.status_registers()}")
        elif cmd == "close":
            g.close(); print(f"  close -> width {g.close_width_mm} mm; {g.status_registers()}")
        elif cmd == "cycle":
            g.open(); print(f"  open  -> {g.status_registers()}")
            g.close(); print(f"  close -> {g.status_registers()}")
            g.open(); print(f"  open  -> {g.status_registers()}")
        elif cmd == "state":
            print(f"  {g.status_registers()}")
    finally:
        g.disconnect()
    return 0


def _run_urcap(cmd: str, ip: str) -> int:
    g = OnRobotURCapGripper(ip)
    print(f"gripper via OnRobot URCap on {ip} (secondary 30002 / primary 30001), "
          f"open={g.open_width_mm}mm close={g.close_width_mm}mm force={g.force_n}N")

    def act(name: str, fn) -> None:
        try:
            fn()
            print(f"  {name} -> ok")
        except Exception as e:
            print(f"  {name} -> FAILED: {e}")
        for line in g.last_messages:
            print(f"      msg: {line}")

    if cmd == "open":
        act("open", g.open)
    elif cmd == "close":
        act("close", g.close)
    elif cmd == "cycle":
        act("open", g.open); act("close", g.close); act("open", g.open)
    elif cmd == "state":
        print(f"  is_closed() -> {g.is_closed()}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] not in ("open", "close", "cycle", "state"):
        print(__doc__); return 2
    cmd = args[0]
    rest = args[1:]
    if "--modbus" in rest:
        i = rest.index("--modbus")
        ip = rest[i + 1] if i + 1 < len(rest) else IP
        return _run_modbus(cmd, ip)
    if "--urcap" in rest:
        i = rest.index("--urcap")
        ip = rest[i + 1] if i + 1 < len(rest) else IP
        return _run_urcap(cmd, ip)
    if "--close-low" in rest and "--single-do" not in rest:
        print("--close-low on its own is deprecated: the app no longer drives the gripper "
              "through a single tool-DO line (it's wired as two lines: DO0=close, DO1=open). "
              "Pass --single-do --close-low to force the old wiring, or drop the flag entirely "
              "to use the default two-line driver.")
        return 2
    if "--single-do" in rest:
        close_high = "--close-low" not in rest
        rest = [a for a in rest if a not in ("--single-do", "--close-low")]
        ip = rest[0] if rest else IP
        return _run_tool_do(cmd, ip, close_high)
    ip = rest[0] if rest else IP
    return _run_dual_do(cmd, ip)


if __name__ == "__main__":
    raise SystemExit(main())
