"""Teach depot/staging/home/transit poses with UR freedrive and write calibration.yaml.

Usage (robot PC, wired to the UR5):
  .venv/bin/python -m hub.kit_study.robotd.teach_poses --ip 192.168.131.140 \
      --out hub/kit_study/configs/calibration.yaml --slots home transit L C R RD1 RD2 OR1 ...
For each name: freedrive is enabled, you move the arm to the grasp pose (jaws around the
brick below the stud), press Enter; q and TCP pose are recorded. Ctrl-C aborts without
writing — freedrive is always ended and the RTDE interfaces are always closed, so the arm
never stays limp after an interrupted session.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from .base import STAGING_SLOTS


def record(ctrl, recv, names: list[str], prompt=None) -> dict:
    """Record one pose per name.

    Freedrive is ended in a ``finally``, so Ctrl-C (or any exception) inside ``prompt``
    still leaves the arm in normal position-control mode instead of limp.
    """
    prompt = prompt or input        # resolved late so tests can patch builtins.input
    cal = {"approach_dz_m": 0.05, "depot": {}, "staging": {}}
    for name in names:
        if not ctrl.teachMode():
            raise RuntimeError(f"could not enable freedrive for {name!r} "
                               "(robot in Remote Control? program running?)")
        try:
            prompt(f"[freedrive ON] move to '{name}' and press Enter… ")
        finally:
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


def _rtde_factory(ip: str):
    import rtde_control, rtde_receive  # lazy: only the robot PC has the lib
    return rtde_control.RTDEControlInterface(ip), rtde_receive.RTDEReceiveInterface(ip)


def _close(iface) -> None:
    try:
        close = getattr(iface, "disconnect", None)
        if close:
            close()
    except Exception:
        pass


def main(argv=None, factory=_rtde_factory) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--slots", nargs="+", required=True)
    ap.add_argument("--merge", action="store_true",
                    help="update only the taught poses inside an existing --out file "
                         "(use it to re-teach one slot without redoing all 19)")
    args = ap.parse_args(argv)
    ctrl, recv = factory(args.ip)
    try:
        cal = record(ctrl, recv, args.slots)
    except KeyboardInterrupt:
        print("\naborted (Ctrl-C) — freedrive ended, robot back in position control; "
              "nothing written")
        return 1
    finally:
        _close(ctrl)
        _close(recv)
    out = Path(args.out)
    if args.merge and out.exists():
        base = yaml.safe_load(out.read_text()) or {}
        base.setdefault("depot", {}).update(cal.get("depot", {}))
        base.setdefault("staging", {}).update(cal.get("staging", {}))
        for name in ("home", "transit", "approach_dz_m"):
            if name in cal and (name != "approach_dz_m" or "approach_dz_m" not in base):
                base[name] = cal[name]
        cal = base
        print(f"merged {len(args.slots)} pose(s) into the existing {out}")
    cal["robot_ip"] = args.ip
    out.write_text(yaml.safe_dump(cal, sort_keys=False))
    print(f"wrote {out} ({len(cal.get('depot', {}))} depot slots, "
          f"{len(cal.get('staging', {}))} staging slots)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
