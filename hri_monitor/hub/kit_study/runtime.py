"""Execution modes: which robot backend + default supply profile the app runs with."""
from __future__ import annotations

import copy
import logging
from pathlib import Path

import yaml

from .robotd.base import RobotBackend, RobotError
from .robotd.sim import SimBackend

MODES_DIR = Path(__file__).parent / "configs" / "mode"
# hub/kit_study/runtime.py -> kit_study -> hub -> hri_monitor (the dir containing run.py)
HRI_MONITOR_ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger(__name__)


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


def resolve_calibration_path(mode_cfg: dict) -> Path:
    """Relative `robot.calibration` paths resolve against the hri_monitor root (where run.py
    lives), not the process cwd — so `run.py --mode robot` behaves the same regardless of
    where it's launched from. Absolute paths pass through unchanged."""
    p = Path(mode_cfg["robot"]["calibration"])
    return p if p.is_absolute() else HRI_MONITOR_ROOT / p


def build_backend(mode_cfg: dict) -> RobotBackend:
    r = mode_cfg["robot"]
    if r["backend"] == "sim":
        return SimBackend(timing=r.get("timing"), failure_rate=float(r.get("failure_rate", 0.0)))
    if r["backend"] == "ur":
        from .robotd.ur import URBackend, load_calibration
        cal_path = resolve_calibration_path(mode_cfg)
        if not cal_path.exists():
            if not r.get("allow_example_calibration"):
                raise RobotError(
                    f"UR calibration file not found: {cal_path}. Teach poses with "
                    "`python -m hub.kit_study.robotd.teach_poses …` or set "
                    "robot.allow_example_calibration: true (URSim rehearsal only)")
            log.warning("UR backend using EXAMPLE calibration — placeholder poses; "
                        "never use on the real robot")
            cal_path = Path(__file__).parent / "configs" / "calibration.example.yaml"
        cal = load_calibration(cal_path)
        return URBackend(r.get("ip") or cal.get("robot_ip"), cal,
                         gripper_settle_s=float(r.get("gripper_settle_s", 1.0)))
    raise ValueError(f"unknown robot backend {r['backend']!r}")
