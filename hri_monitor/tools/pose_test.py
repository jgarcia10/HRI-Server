#!/usr/bin/env python3
"""Exercise the taught poses with the app's own URBackend: pick from a depot slot, place on a
staging slot, one slot at a time, with the operator watching.

    .venv/bin/python tools/pose_test.py --slots RD1                 # one slot
    .venv/bin/python tools/pose_test.py --slots RD1 RD2 RD3 --to L  # a few, released on L
    .venv/bin/python tools/pose_test.py --all                       # all 14, pausing between
    .venv/bin/python tools/pose_test.py --all --no-gripper          # motion only, jaws untouched

Every motion is the real thing: transit → 5 cm above the slot → straight down → gripper →
straight up → transit → above the staging slot → down → release → up. Errors are reported with
the backend's own message (unreachable target, IK off the taught branch, protective stop…).

KEEP A HAND ON THE E-STOP. Start with one slot before running --all.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hub.kit_study.robotd.base import RobotError  # noqa: E402
from hub.kit_study.runtime import build_backend, load_mode  # noqa: E402

ORDER = ["RD1", "RD2", "RD3", "OR1", "OR2", "OR3", "BL1", "BL2",
         "SF1", "SF2", "SF3", "LM1", "LM2", "LM3"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default=None, help="override the IP in configs/mode/robot.yaml")
    ap.add_argument("--slots", nargs="*", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--to", default="C", choices=["L", "C", "R"], help="staging slot to release on")
    ap.add_argument("--pace", default="slow", choices=["slow", "normal"])
    ap.add_argument("--no-gripper", action="store_true", help="move only; never touch the jaws")
    ap.add_argument("--no-home", action="store_true", help="skip the initial home()")
    ap.add_argument("--settle", type=float, default=6.5,
                    help="seconds the gripper is given to travel (jaws start fully open ~110 mm; "
                         "reaching a 32 mm brick needs ~5 s of the ~7 s full stroke)")
    ap.add_argument("--yes", action="store_true", help="do not pause between slots")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="    · %(message)s")

    slots = ORDER if args.all else (args.slots or [])
    if not slots:
        print(__doc__); return 2

    cfg = load_mode("robot", overrides={"robot": {"ip": args.ip}} if args.ip else None)
    backend = build_backend(cfg)
    backend.settle = float(args.settle)          # closing: jaws travel from fully open
    if args.no_gripper:                      # swap in a no-op actuator, jaws never move
        class _Frozen:
            name = "frozen"
            def connect(self): pass
            def disconnect(self): pass
            def open(self): print("        (gripper: abrir — omitido)")
            def close(self): print("        (gripper: cerrar — omitido)")
            def is_closed(self): return False
            def grip_detected(self): return None
        backend.gripper = _Frozen()

    print(f"conectando a {backend.ip} …  (cierre {backend.settle:.1f} s · apertura "
          f"{backend.open_settle:.1f} s · ritmo {args.pace})")
    backend.connect()
    backend.set_pace(args.pace)
    ok, failed = [], []
    try:
        if not args.no_home:
            print("home …"); backend.home()
        for i, slot in enumerate(slots, 1):
            print(f"\n[{i}/{len(slots)}] {slot} → {args.to}")
            t0 = time.time()
            try:
                backend.pick(slot)
                t_pick = time.time() - t0
                print(f"    pick  ok  ({t_pick:.1f} s)")
                backend.place(args.to)
                print(f"    place ok  ({time.time() - t0 - t_pick:.1f} s)   total {time.time()-t0:.1f} s")
                ok.append(slot)
            except RobotError as e:
                print(f"    ✘ {type(e).__name__}: {e}")
                failed.append((slot, str(e)))
                if input("    ¿seguir con el siguiente? [s/N] ").strip().lower() not in ("s", "y"):
                    break
                continue
            if not args.yes and i < len(slots):
                a = input(f"    retira la pieza de {args.to} y devuélvela a {slot}; "
                          "Enter = siguiente · r = repetir este · q = salir: ").strip().lower()
                if a == "q":
                    break
                if a == "r":
                    slots.insert(i, slot)
    except KeyboardInterrupt:
        print("\ninterrumpido")
    finally:
        try:
            backend.stop()
        except Exception:
            pass
        backend.disconnect()
    print(f"\nresumen: {len(ok)} ok {ok}")
    if failed:
        print("fallaron:")
        for s, e in failed:
            print(f"   {s}: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
