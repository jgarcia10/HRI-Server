#!/usr/bin/env python3
"""Definitive on-site check of the RG2 v2 in tool-DO mode (pendant: tool output "controlled by
user"; DO0 = 1 opens, DO0 = 0 closes). Run from hri_monitor/:

    .venv/bin/python tools/gripper_check.py [robot_ip]          # full check (writes DO0 open/close)
    .venv/bin/python tools/gripper_check.py --watch             # live state only, writes nothing

Prints a verdict per step. It only writes tool DO0 (what the app does) and leaves it at 1 (open).

IMPORTANT: after any loss of tool power the RG2 ignores DO0 until the OnRobot URCap has
initialised it once: pendant Installation → I/O → tool output "controlled by OnRobot" (gripper
closes) → back to "controlled by user" → File → Save. Never power-cycle the tool from software.
"""
import socket
import struct
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
IP = next((a for a in ARGS if a.count(".") == 3), "147.250.35.40")   # ignore stray words like "cycle"
WATCH = "--watch" in sys.argv
OK, BAD, INFO = "\033[32m✔\033[0m", "\033[31m✘\033[0m", "  ·"


class ToolStream(threading.Thread):
    """Keeps the secondary-interface stream open and exposes the latest ToolData (10 Hz)."""

    def __init__(self, ip):
        super().__init__(daemon=True)
        self.ip = ip; self.latest = None; self.stop = threading.Event(); self.samples = []

    def run(self):
        s = socket.create_connection((self.ip, 30002), timeout=3); buf = b""
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
                if mtype != 16:
                    continue
                i = 0
                while i + 5 <= len(msg):
                    psize, ptype = struct.unpack(">IB", msg[i:i + 5])
                    body = msg[i + 5:i + psize]
                    if ptype == 2 and len(body) >= 32:
                        f = struct.unpack(">BBddfBffB", body[:32])
                        self.latest = {"t": time.time(), "ai0": f[2], "ai1": f[3], "volt": f[5],
                                       "cur": f[6], "temp": f[7]}
                        self.samples.append(self.latest)
                    i += psize
        s.close()


def label(td, di_bits, do_bits):
    """Rough state label from the signatures seen on site (RG2 v2 on the CB3 tool connector)."""
    if td["volt"] != 24:
        return "NO TOOL POWER"
    if td["ai0"] > 9.0 and (di_bits & 0b10):
        return "READY (initialised; DO0 should work)"
    if td["ai0"] < 1.0:
        return "UNINITIALISED (just powered; needs the OnRobot init once)"
    return "electronics alive, no valid handshake"


def watch() -> int:
    """Live view while you work on the pendant / Quick Changer. Ctrl-C to stop. Writes nothing."""
    import rtde_receive
    recv = rtde_receive.RTDEReceiveInterface(IP)
    stream = ToolStream(IP); stream.start(); time.sleep(1.5)
    print(f"watching {IP} — Ctrl-C to stop")
    try:
        while True:
            td = stream.latest
            do_b = int(recv.getActualDigitalOutputBits()) >> 16 & 0b11
            di_b = int(recv.getActualDigitalInputBits()) >> 16 & 0b11
            if td:
                print(f"{time.strftime('%H:%M:%S')}  {td['volt']:>2} V {td['cur']:.3f} A {td['temp']:.0f}°C  "
                      f"AI0 {td['ai0']:5.2f} V  AI1 {td['ai1']:5.2f} V  DO1:0={do_b:02b}  DI1:0={di_b:02b}   {label(td, di_b, do_b)}", flush=True)
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop.set(); recv.disconnect()
    return 0


def main() -> int:
    if WATCH:
        return watch()
    import rtde_io, rtde_receive
    recv = rtde_receive.RTDEReceiveInterface(IP)
    io = rtde_io.RTDEIOInterface(IP)
    stream = ToolStream(IP); stream.start(); time.sleep(1.5)
    do0 = lambda: int(recv.getActualDigitalOutputBits()) >> 16 & 1
    dobits = lambda: int(recv.getActualDigitalOutputBits()) >> 16 & 0b11
    di = lambda: int(recv.getActualDigitalInputBits()) >> 16 & 0b11
    verdicts = []

    print(f"RG2 v2 check on {IP} — tool DO0 mode (1 = open, 0 = close)")
    td = stream.latest
    if not td:
        print(f"{BAD} no tool data on the secondary interface"); return 1
    powered = td["volt"] == 24 and td["cur"] > 0.03
    print(f"{OK if powered else BAD} tool connector: {td['volt']} V, {td['cur']:.3f} A, {td['temp']:.0f} °C"
          + ("" if powered else "  → set tool output voltage to 24 V on the pendant (Installation → I/O)"))
    verdicts.append(powered)

    # 1. is anything else driving DO0?  (the OnRobot daemon toggles it as its comm line)
    seen = set(); t0 = time.time()
    while time.time() - t0 < 3.0:
        seen.add(dobits()); time.sleep(0.05)
    quiet = len(seen) == 1
    print(f"{OK if quiet else BAD} tool DO1:DO0 left alone for 3 s: {'stable at %02b' % seen.pop() if quiet else 'CHANGING by themselves'}"
          + ("" if quiet else "  → the OnRobot URCap daemon owns the tool output: pendant Installation → I/O → tool output 'controlled by user', then File → Save"))
    verdicts.append(quiet)

    # 2. do our writes take effect and stick?
    ok = True
    for level in (True, False, True):
        io.setToolDigitalOut(0, level); time.sleep(0.6)
        if do0() != int(level):
            ok = False
    print(f"{OK if ok else BAD} our writes reach DO0 and stick" + ("" if ok else "  → something overrides DO0 (URCap daemon or a running program)"))
    verdicts.append(ok)

    # 3. open / close / open with 10 Hz logging of current, AI0/AI1 and tool DI
    def phase(level, label, secs=3.0):
        stream.samples.clear(); dis = set()
        io.setToolDigitalOut(0, level)
        t0 = time.time()
        while time.time() - t0 < secs:
            dis.add(di()); time.sleep(0.05)
        s = list(stream.samples)
        cur = [x["cur"] for x in s]; a0 = [x["ai0"] for x in s]; a1 = [x["ai1"] for x in s]
        rest = s[-3:]
        out = {"label": label, "cur_max": max(cur) if cur else 0, "cur_rest": rest[-1]["cur"] if rest else 0,
               "ai0_rest": sum(x["ai0"] for x in rest) / len(rest) if rest else 0,
               "ai1_rest": sum(x["ai1"] for x in rest) / len(rest) if rest else 0,
               "ai0_range": (min(a0), max(a0)) if a0 else (0, 0), "di": sorted(dis)}
        print(f"{INFO} {label:<14} DO0={do0()}  current max {out['cur_max']:.3f} A → rest {out['cur_rest']:.3f} A"
              f"   AI0 {out['ai0_range'][0]:.2f}…{out['ai0_range'][1]:.2f} → rest {out['ai0_rest']:.2f} V"
              f"   AI1 rest {out['ai1_rest']:.2f} V   tool DI states {out['di']}")
        return out
    o1 = phase(True, "OPEN  (DO0=1)"); c1 = phase(False, "CLOSE (DO0=0)"); o2 = phase(True, "OPEN  (DO0=1)")

    moved_cur = max(c1["cur_max"], o2["cur_max"]) > max(o1["cur_rest"], c1["cur_rest"]) + 0.08
    fb_ai = abs(c1["ai0_rest"] - o2["ai0_rest"]) > 0.5 or abs(c1["ai1_rest"] - o2["ai1_rest"]) > 0.5
    fb_di = c1["di"] != o2["di"]
    print(f"{OK if moved_cur else BAD} motor current transient on close/open: {'yes' if moved_cur else 'not seen (sampling 10 Hz; trust your eyes)'}")
    print(f"{OK if (fb_ai or fb_di) else BAD} gripper feedback differs open vs closed: "
          f"{'AI' if fb_ai else ''}{' ' if fb_ai and fb_di else ''}{'DI' if fb_di else ''}{'none' if not (fb_ai or fb_di) else ''}")
    verdicts.append(moved_cur or fb_ai or fb_di)

    stream.stop.set(); recv.disconnect(); io.disconnect()
    print("left DO0 = 1 (open).")
    if all(verdicts):
        print(f"\n{OK} VERDICT: gripper responds to tool DO0 from the laptop — the app's `tool_do, close_high: false` will work.")
        return 0
    print(f"\n{BAD} VERDICT: not confirmed — see the ✘ lines above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
