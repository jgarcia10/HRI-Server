#!/usr/bin/env python3
"""Toggle the gripper through the UR tool digital output (the app's own mapping) — the first
thing to check on site: does the OnRobot actually open/close on tool DO0?

    .venv/bin/python tools/gripper_test.py open          # DO0 = False
    .venv/bin/python tools/gripper_test.py close         # DO0 = True
    .venv/bin/python tools/gripper_test.py cycle         # open, close, open (1.5 s apart)
    .venv/bin/python tools/gripper_test.py state         # read DO0 back, no actuation
    .venv/bin/python tools/gripper_test.py cycle --close-low   # lab RG2 v2: DO0=1 opens, DO0=0 closes

If nothing moves, the OnRobot is driven another way (URCap / Compute Box Modbus) and
URBackend.pick/open_gripper need a different actuator — note the gripper model.

`--modbus IP` drives the OnRobot Compute Box directly over Modbus TCP (port 502, unit id 65),
bypassing the UR tool connector entirely — use this to check the box from the laptop without
going through the app or the URCap:

    .venv/bin/python tools/gripper_test.py open  --modbus 192.168.1.1
    .venv/bin/python tools/gripper_test.py close --modbus 192.168.1.1
    .venv/bin/python tools/gripper_test.py cycle --modbus 192.168.1.1
    .venv/bin/python tools/gripper_test.py state --modbus 192.168.1.1   # raw status/width regs

`--urcap [IP]` drives the OnRobot unified URCap's rg_grip(...) the way the app does once the
URCap is (re)installed on the pendant: sends a one-shot URScript program over the UR's secondary
interface (30002) and watches the primary interface (30001) for completion — no separate box
IP, it talks straight to the robot controller. Prints every RobotMessage text it captured, so a
"Missing URCap" / "No RG gripper connected" popup on the pendant shows up here too:

    .venv/bin/python tools/gripper_test.py open  --urcap
    .venv/bin/python tools/gripper_test.py close --urcap
    .venv/bin/python tools/gripper_test.py cycle --urcap
    .venv/bin/python tools/gripper_test.py open  --urcap 147.250.35.40   # explicit robot IP
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hub.kit_study.robotd.gripper import OnRobotModbusGripper, OnRobotURCapGripper  # noqa: E402
from hub.kit_study.robotd.ur import GRIPPER_TOOL_DO  # noqa: E402

IP = "147.250.35.40"


def _run_tool_do(cmd: str, ip: str, close_high: bool = True) -> int:
    """close_high=False → DO0=0 closes, DO0=1 opens (the lab RG2 v2 in user-controlled tool-output mode)."""
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
    print(f"gripper via tool DO{GRIPPER_TOOL_DO} on {ip}; DO0 currently {do0()}")
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
    close_high = "--close-low" not in rest
    rest = [a for a in rest if a != "--close-low"]
    ip = rest[0] if rest else IP
    return _run_tool_do(cmd, ip, close_high)


if __name__ == "__main__":
    raise SystemExit(main())
