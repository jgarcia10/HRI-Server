#!/usr/bin/env python3
"""Read (and optionally set) the UR tool-connector output voltage — the OnRobot gripper is
powered from it, so 0 V here means "URCap says no gripper" and DO0 does nothing.

    .venv/bin/python tools/tool_voltage.py            # read ToolData from the 30002 stream
    .venv/bin/python tools/tool_voltage.py 24         # set_tool_voltage(24) then re-read
"""
import socket, struct, sys, time

IP = "147.250.35.40"


def read_tool_data(ip=IP, timeout=3.0):
    """One RobotState (msg type 16) → its ToolData sub-package (type 2)."""
    s = socket.create_connection((ip, 30002), timeout=timeout)
    buf = b""; t0 = time.time()
    try:
        while time.time() - t0 < timeout:
            buf += s.recv(4096)
            while len(buf) >= 5:
                size, mtype = struct.unpack(">IB", buf[:5])
                if len(buf) < size:
                    break
                msg, buf = buf[5:size], buf[size:]
                if mtype != 16:
                    continue
                i = 0
                while i + 5 <= len(msg):
                    psize, ptype = struct.unpack(">IB", msg[i:i + 5])
                    body = msg[i + 5:i + psize]
                    if ptype == 2 and len(body) >= 32:
                        f = struct.unpack(">BBddfBffB", body[:32])
                        return {"analog_range": (f[0], f[1]), "analog_in": (round(f[2], 3), round(f[3], 3)),
                                "tool_48V": round(f[4], 2), "tool_output_voltage_V": f[5],
                                "tool_current_A": round(f[6], 3), "tool_temp_C": round(f[7], 1),
                                "tool_mode": f[8]}
                    i += psize
    finally:
        s.close()
    return None


def send_script(line, ip=IP):
    s = socket.create_connection((ip, 30002), timeout=3); s.sendall((line + "\n").encode()); time.sleep(0.5); s.close()


if __name__ == "__main__":
    print("tool data:", read_tool_data())
    if len(sys.argv) > 1:
        v = int(sys.argv[1]); assert v in (0, 12, 24)
        print(f"→ set_tool_voltage({v})"); send_script(f"set_tool_voltage({v})"); time.sleep(1.5)
        print("tool data:", read_tool_data())
