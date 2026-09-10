#!/usr/bin/env python3
"""Toggle the gripper through the UR tool digital output (the app's own mapping) — the first
thing to check on site: does the OnRobot actually open/close on tool DO0?

    .venv/bin/python tools/gripper_test.py open          # DO0 = False
    .venv/bin/python tools/gripper_test.py close         # DO0 = True
    .venv/bin/python tools/gripper_test.py cycle         # open, close, open (1.5 s apart)
    .venv/bin/python tools/gripper_test.py state         # read DO0 back, no actuation

If nothing moves, the OnRobot is driven another way (URCap / Compute Box Modbus) and
URBackend.pick/open_gripper need a different actuator — note the gripper model.

`--modbus IP` drives the OnRobot Compute Box directly over Modbus TCP (port 502, unit id 65),
bypassing the UR tool connector entirely — use this to check the box from the laptop without
going through the app or the URCap:

    .venv/bin/python tools/gripper_test.py open  --modbus 192.168.1.1
    .venv/bin/python tools/gripper_test.py close --modbus 192.168.1.1
    .venv/bin/python tools/gripper_test.py cycle --modbus 192.168.1.1
    .venv/bin/python tools/gripper_test.py state --modbus 192.168.1.1   # raw status/width regs
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hub.kit_study.robotd.gripper import OnRobotModbusGripper  # noqa: E402
from hub.kit_study.robotd.ur import GRIPPER_TOOL_DO  # noqa: E402

IP = "147.250.35.40"


def _run_tool_do(cmd: str, ip: str) -> int:
    import rtde_io, rtde_receive
    io = rtde_io.RTDEIOInterface(ip)
    recv = rtde_receive.RTDEReceiveInterface(ip)
    def do0():
        bits = int(recv.getActualDigitalOutputBits())
        return bool(bits >> (16 + GRIPPER_TOOL_DO) & 1)      # tool DOs are bits 16-17
    def set_(close: bool):
        ok = io.setToolDigitalOut(GRIPPER_TOOL_DO, close)
        time.sleep(1.5)
        print(f"  setToolDigitalOut({GRIPPER_TOOL_DO}, {close}) -> {ok}; DO0 reads {do0()}")
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
    ip = rest[0] if rest else IP
    return _run_tool_do(cmd, ip)


if __name__ == "__main__":
    raise SystemExit(main())
