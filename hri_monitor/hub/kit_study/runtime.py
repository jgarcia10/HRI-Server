"""Execution modes: which robot backend + default supply profile the app runs with."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

from .robotd.base import RobotBackend
from .robotd.sim import SimBackend

MODES_DIR = Path(__file__).parent / "configs" / "mode"


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_mode(name_or_path: str, overrides: dict | None = None) -> dict:
    p = Path(name_or_path)
    if not p.suffix:
        p = MODES_DIR / f"{name_or_path}.yaml"
    cfg = yaml.safe_load(p.read_text())
    return _merge(cfg, overrides or {})


def build_backend(mode_cfg: dict) -> RobotBackend:
    r = mode_cfg["robot"]
    if r["backend"] == "sim":
        return SimBackend(timing=r.get("timing"), failure_rate=float(r.get("failure_rate", 0.0)))
    if r["backend"] == "ur":
        from .robotd.ur import URBackend, load_calibration
        cal_path = r["calibration"]
        cal = load_calibration(cal_path) if Path(cal_path).exists() else \
              load_calibration(Path(__file__).parent / "configs" / "calibration.example.yaml")
        return URBackend(r.get("ip") or cal.get("robot_ip"), cal,
                         gripper_settle_s=float(r.get("gripper_settle_s", 1.0)))
    raise ValueError(f"unknown robot backend {r['backend']!r}")
