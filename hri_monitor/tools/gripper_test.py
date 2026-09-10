#!/usr/bin/env python3
"""Toggle the gripper through the UR tool digital output (the app's own mapping) — the first
thing to check on site: does the OnRobot actually open/close on tool DO0?

    .venv/bin/python tools/gripper_test.py open          # DO0 = False
    .venv/bin/python tools/gripper_test.py close         # DO0 = True
    .venv/bin/python tools/gripper_test.py cycle         # open, close, open (1.5 s apart)
    .venv/bin/python tools/gripper_test.py state         # read DO0 back, no actuation

If nothing moves, the OnRobot is driven another way (URCap / Compute Box Modbus) and
URBackend.pick/open_gripper need a different actuator — note the gripper model.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hub.kit_study.robotd.ur import GRIPPER_TOOL_DO  # noqa: E402

IP = "147.250.35.40"


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("open", "close", "cycle", "state"):
        print(__doc__); return 2
    ip = sys.argv[2] if len(sys.argv) > 2 else IP
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
    cmd = sys.argv[1]
    print(f"gripper via tool DO{GRIPPER_TOOL_DO} on {ip}; DO0 currently {do0()}")
    if cmd == "open":
        set_(False)
    elif cmd == "close":
        set_(True)
    elif cmd == "cycle":
        set_(False); set_(True); set_(False)
    recv.disconnect(); io.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
