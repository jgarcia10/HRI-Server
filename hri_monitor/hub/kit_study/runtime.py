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


def build_gripper(gripper_cfg: dict | None, robot_ip: str | None = None):
    """robot.gripper config -> a Gripper instance, a *factory* for `URBackend` to bind to its
    own RTDE interfaces, or None to let `URBackend` build its own default ToolDOGripper (bound
    to the backend's own RTDE IO interface, so reconnects work).

    `kind: tool_do` (default) — UR tool digital output 0; needs the OnRobot URCap connected to
    the Compute Box and configured for digital I/O control.
    `kind: dual_do` — the lab's actual wiring (measured 2026-09-10/11): two tool digital outputs
    are the two directions of an H-bridge inside the gripper (`close_do`/`open_do`, default 0/1).
    Like `tool_do` this must bind to the backend's own (reconnect-replaceable) RTDE IO/receive
    interfaces, so this returns a *factory* `callable(io_getter, recv_getter=None) -> Gripper`
    rather than a built instance — `URBackend.__init__` calls it with its own getters. Optional
    `settle_s`/`hold_close` override the `DualDOGripper` defaults.
    `kind: onrobot_modbus` — direct Modbus TCP to the OnRobot Compute Box; works regardless of
    URCap wiring. Requires `ip`; `port`/`unit_id`/`force_n`/`open_width_mm`/`close_width_mm`/
    `settle_s` are optional overrides.
    `kind: onrobot_urcap` — drives the OnRobot unified URCap's `rg_grip(...)` through a one-shot
    URScript program sent to the controller itself, so it talks to `robot_ip` (the UR, not a
    separate box) unless `ip` overrides it. `force_n`/`open_width_mm`/`close_width_mm`/
    `timeout_s`/`script_path` are optional overrides.
    """
    cfg = gripper_cfg or {}
    kind = cfg.get("kind", "tool_do")
    if kind == "tool_do":
        return None
    if kind == "dual_do":
        from .robotd.gripper import DualDOGripper
        kwargs = {k: cfg[k] for k in ("close_do", "open_do", "settle_s", "hold_close") if k in cfg}

        def factory(io_getter, recv_getter=None):
            return DualDOGripper(io_getter, recv_getter=recv_getter, **kwargs)
        return factory
    if kind == "onrobot_modbus":
        from .robotd.gripper import OnRobotModbusGripper
        kwargs = {k: cfg[k] for k in
                  ("port", "unit_id", "force_n", "open_width_mm", "close_width_mm", "settle_s")
                  if k in cfg}
        return OnRobotModbusGripper(ip=cfg["ip"], **kwargs)
    if kind == "onrobot_urcap":
        from .robotd.gripper import OnRobotURCapGripper
        kwargs = {k: cfg[k] for k in
                  ("force_n", "open_width_mm", "close_width_mm", "timeout_s", "script_path")
                  if k in cfg}
        return OnRobotURCapGripper(ip=cfg.get("ip", robot_ip), **kwargs)
    raise ValueError(f"unknown gripper kind {kind!r}")


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
        robot_ip = r.get("ip") or cal.get("robot_ip")
        gcfg = r.get("gripper") or {}
        return URBackend(robot_ip, cal,
                         speeds=r.get("speeds"),
                         gripper_settle_s=float(r.get("gripper_settle_s", 1.0)),
                         gripper_open_settle_s=(float(r["gripper_open_settle_s"])
                                                if "gripper_open_settle_s" in r else None),
                         gripper=build_gripper(gcfg, robot_ip=robot_ip),
                         gripper_close_high=bool(gcfg.get("close_high", True)))
    raise ValueError(f"unknown robot backend {r['backend']!r}")
