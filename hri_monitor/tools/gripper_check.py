#!/usr/bin/env python3
"""Definitive on-site check of the RG2 v2 in tool-DO mode (pendant: tool output "controlled by
user"; DO0 = 1 opens, DO0 = 0 closes). Run from hri_monitor/:

    .venv/bin/python tools/gripper_check.py [robot_ip]          # full check (writes DO0 open/close)
    .venv/bin/python tools/gripper_check.py --watch             # live state only, writes nothing
    .venv/bin/python tools/gripper_check.py --matrix            # all 4 combinations (short dwells)
    .venv/bin/python tools/gripper_check.py --pulse             # self-timed open/close x2, what the app does

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
MATRIX = "--matrix" in sys.argv
PULSE = "--pulse" in sys.argv
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


def matrix() -> int:
    """All four tool-output combinations (2024 names: DO0 = close, DO1 = soft) with 5 s dwell.

    The decisive number is the tool current: an RG2 that is listening draws ~130-145 mA while a
    control line is active, versus ~85 mA idle. Identical current in all four rows means the
    control line is not reaching the gripper at all (contacts / cable), whatever the pendant says.
    """
    import rtde_io, rtde_receive
    recv = rtde_receive.RTDEReceiveInterface(IP); io = rtde_io.RTDEIOInterface(IP)
    st = ToolStream(IP); st.start(); time.sleep(1.5)
    print("DO1(open) DO0(close) | tool current  |  AI0   AI1  | tool DI seen     moving = ~0.13 A, fault = AI1 6.4 V")
    rows = []
    # NEVER (1, 1): DO0 = close and DO1 = open are the two directions of an H-bridge; asserting
    # both latches a gripper fault that survives a power cycle (learned the hard way 2026-09-10).
    for d1, d0 in ((False, False), (False, True), (False, False), (True, False)):
        if True:
            io.setToolDigitalOut(1 if d0 else 0, False); time.sleep(0.15)   # break before make
            io.setToolDigitalOut(1, d1); io.setToolDigitalOut(0, d0)
            st.samples.clear(); dis = set(); t0 = time.time()
            while time.time() - t0 < 1.5:   # never hold a direction for seconds: it stalls the motor
                dis.add(int(recv.getActualDigitalInputBits()) >> 16 & 0b11); time.sleep(0.05)
            s = list(st.samples); cur = [x["cur"] for x in s]
            rows.append(max(cur))
            print(f"   {int(d1)}         {int(d0)}      | {min(cur):.3f}-{max(cur):.3f} A | {s[-1]['ai0']:5.2f} {s[-1]['ai1']:5.2f} | {sorted(dis)}")
    io.setToolDigitalOut(0, False); io.setToolDigitalOut(1, False)    # leave NEUTRAL: never hold a direction
    st.stop.set(); recv.disconnect(); io.disconnect()
    spread = max(rows) - min(rows)
    print(f"\n{OK if spread > 0.03 else BAD} current spread across the four combinations: {spread*1000:.0f} mA"
          + ("" if spread > 0.03 else "  → no control line reaches the gripper: power off and re-seat the Quick Changer (RUNBOOK C.3)"))
    return 0 if spread > 0.03 else 1


def smart_pulse(io, st, close: bool, max_s: float = 3.0, idle_a: float = 0.095):
    """Assert one direction, release as soon as the motor current falls back to idle.

    Holding a direction after the fingers reach their stop stalls the motor and latches the
    gripper fault (AI1 ~6.4 V), so the command is never held longer than the motion needs.
    Break-before-make; never both lines high; always ends neutral.
    """
    other, want = (1, 0) if close else (0, 1)
    io.setToolDigitalOut(other, False); time.sleep(0.15)
    st.samples.clear()
    t0 = time.time(); io.setToolDigitalOut(want, True)
    moved = False; stop_t = None
    while time.time() - t0 < max_s:
        s = st.latest
        if s["cur"] > idle_a:
            moved = True
        elif moved:
            stop_t = time.time() - t0; break
        if s["ai1"] > 5.0:
            break
        time.sleep(0.02)
    io.setToolDigitalOut(want, False)
    time.sleep(0.4)
    s = st.latest
    cur = [x["cur"] for x in st.samples] or [0]
    state = "FAULT" if s["ai1"] > 5 else ("dark" if s["ai0"] < 1 else "ready" if s["ai1"] < 2 else "moving")
    print(f"  {'CLOSE' if close else 'OPEN ':<5}  held {(stop_t or (time.time()-t0)):.2f} s"
          f"  current {min(cur):.3f}-{max(cur):.3f} A  {'(motion seen)' if moved else '(NO motion)'}"
          f"   AI0 {s['ai0']:5.2f} AI1 {s['ai1']:5.2f}  {state}", flush=True)
    return moved and s["ai1"] < 5


def pulse_mode() -> int:
    """Close/open twice with self-timed pulses — the sequence the app will use."""
    import rtde_io
    io = rtde_io.RTDEIOInterface(IP)
    io.setToolDigitalOut(0, False); io.setToolDigitalOut(1, False)
    st = ToolStream(IP); st.start(); time.sleep(1.5)
    s = st.latest
    print(f"start: AI0 {s['ai0']:.2f} AI1 {s['ai1']:.2f} {s['cur']:.3f} A")
    if s["ai0"] < 1:
        print(f"{BAD} gripper is dark — wake it on the pendant (tool output controlled by OnRobot, then by user)")
        st.stop.set(); io.disconnect(); return 1
    if s["ai1"] > 5:
        print(f"{BAD} gripper is FAULTED — see the recovery protocol in RUNBOOK_robot.md C.3")
        st.stop.set(); io.disconnect(); return 1
    ok = True
    for close in (True, False, True, False):
        ok = smart_pulse(io, st, close) and ok
        time.sleep(0.8)
    io.setToolDigitalOut(0, False); io.setToolDigitalOut(1, False)
    st.stop.set(); io.disconnect()
    print(f"\n{OK if ok else BAD} " + ("two full open/close cycles, no fault — this is what the app does" if ok
          else "at least one command did not move the gripper or it faulted"))
    return 0 if ok else 1


def main() -> int:
    if WATCH:
        return watch()
    if PULSE:
        return pulse_mode()
    if MATRIX:
        return matrix()
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
    print(f"{OK if quiet else BAD} tool DO1:DO0 left alone for 3 s: {('stable at ' + format(seen.pop(), '02b')) if quiet else 'CHANGING by themselves'}"
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
