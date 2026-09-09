"""Teach depot/staging/home/transit poses with UR freedrive and write calibration.yaml.

Usage (robot PC, wired to the UR5):
  .venv/bin/python -m hub.kit_study.robotd.teach_poses --ip 192.168.131.140 \
      --out hub/kit_study/configs/calibration.yaml --slots home transit L C R RD1 RD2 OR1 ...
For each name: freedrive is enabled, you move the arm to the grasp pose (jaws around the
brick below the stud), press Enter; q and TCP pose are recorded. Ctrl-C aborts without writing.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from .base import STAGING_SLOTS


def record(ctrl, recv, names: list[str], prompt=input) -> dict:
    cal = {"approach_dz_m": 0.05, "depot": {}, "staging": {}}
    for name in names:
        ctrl.teachMode()
        prompt(f"[freedrive ON] move to '{name}' and press Enter… ")
        ctrl.endTeachMode()
        node = {"q": [float(x) for x in recv.getActualQ()],
                "pose": [float(x) for x in recv.getActualTCPPose()]}
        if name in ("home", "transit"):
            cal[name] = {"q": node["q"]}
        elif name in STAGING_SLOTS:
            cal["staging"][name] = node
        else:
            cal["depot"][name] = node
    return cal


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--slots", nargs="+", required=True)
    args = ap.parse_args(argv)
    import rtde_control, rtde_receive
    ctrl = rtde_control.RTDEControlInterface(args.ip)
    recv = rtde_receive.RTDEReceiveInterface(args.ip)
    cal = record(ctrl, recv, args.slots)
    cal["robot_ip"] = args.ip
    Path(args.out).write_text(yaml.safe_dump(cal, sort_keys=False))
    print(f"wrote {args.out} ({len(cal['depot'])} depot slots, {len(cal['staging'])} staging slots)")


if __name__ == "__main__":
    main()
