import logging
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hub.bus import MessageBus
from hub.experiments.controller import RecordingController
from hub.experiments.db import Database
from hub.kit_study.robotd.base import RobotError
from hub.kit_study.robotd.ur import URBackend
from hub.kit_study.runtime import build_backend, load_mode, resolve_calibration_path
from hub.server import create_app

HRI_MONITOR_ROOT = Path(__file__).resolve().parent.parent


class FakeManager:
    config = {"sensors": {}}
    def statuses(self):
        return {}


FAST = {"robot": {"backend": "sim", "timing": {"home": 0.005, "pick": 0.005, "place": 0.005,
                                               "open_gripper": 0.005, "noise_std": 0.0}},
        "supply": {"lookahead": 2, "side": "L", "pace": "normal", "announce": False}}


@pytest.fixture
def client(tmp_path):
    bus = MessageBus()
    db = Database(tmp_path / "hri.db")
    ctrl = RecordingController(bus, db, tmp_path / "recordings")
    app = create_app(bus, FakeManager(), ui_dir=None, config_path=tmp_path / "c.yaml",
                     experiments={"db": db, "controller": ctrl}, kit_mode=FAST)
    with TestClient(app) as c:
        yield c
    kit = app.state.kit_session
    if kit.status() is not None:
        kit.stop()
    app.state.robot_bridge.stop()


def wait(c, pred, timeout=3.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred(c.get("/api/kit/state").json()):
            return True
        time.sleep(0.02)
    return False


def test_mode_loading_and_backend():
    cfg = load_mode("sim")
    assert cfg["robot"]["backend"] == "sim"
    assert build_backend(cfg).name == "sim"
    cfg = load_mode("robot", overrides={"robot": {"ip": "10.0.0.9"}})
    assert cfg["robot"]["backend"] == "ur" and cfg["robot"]["ip"] == "10.0.0.9"


def test_robot_state_and_home(client):
    st = client.get("/api/kit/robot/state").json()
    assert st["backend"] == "sim" and st["connected"] is True
    r = client.post("/api/kit/robot/home")
    assert r.status_code == 200 and "job_id" in r.json()


def test_session_runs_supply_with_profile(client):
    r = client.post("/api/kit/session/start",
                    json={"participant_code": "P01", "condition": "C0", "profile": {"lookahead": 2, "side": "R"}})
    assert r.status_code == 200
    assert wait(client, lambda s: len(s["session"]["supply"]["staged"]) == 2)
    assert "R" in client.get("/api/kit/supply/state").json()["staged"]
    client.post("/api/kit/event", json={"type": "part_placed"})
    assert wait(client, lambda s: "F1O1P3" in s["session"]["supply"]["staged"].values())
    r = client.post("/api/kit/supply/profile", json={"lookahead": 0})
    assert r.status_code == 200 and r.json()["profile"]["lookahead"] == 0
    client.post("/api/kit/session/stop")


def test_request_part_event_and_estop_latches_until_home(client):
    client.post("/api/kit/session/start",
                json={"participant_code": "P02", "condition": "C1", "profile": {"lookahead": 0}})
    time.sleep(0.1)
    assert client.get("/api/kit/supply/state").json()["staged"] == {}
    assert client.post("/api/kit/event", json={"type": "request_part"}).status_code == 200
    assert wait(client, lambda s: len(s["session"]["supply"]["staged"]) == 1)

    r = client.post("/api/kit/robot/stop")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["state"]["latched"] == "estop"
    st = client.get("/api/kit/robot/state").json()
    assert st["queue"] == 0 and st["latched"] == "estop"

    # C1: a further request must not put the robot back in motion
    client.post("/api/kit/event", json={"type": "request_part"})
    time.sleep(0.2)
    sup = client.get("/api/kit/supply/state").json()
    assert len(sup["staged"]) == 1 and sup["paused"] is True
    assert sup["blocked"]["reason"] == "estop"

    # home clears the latch and supply works again
    assert client.post("/api/kit/robot/home").json()["ok"] is True
    assert wait(client, lambda s: s["session"]["supply"]["paused"] is False)
    assert client.get("/api/kit/robot/state").json()["latched"] is None
    client.post("/api/kit/event", json={"type": "part_placed"})
    client.post("/api/kit/event", json={"type": "request_part"})
    assert wait(client, lambda s: "F1O1P2" in s["session"]["supply"]["staged"].values())
    assert client.get("/api/kit/supply/state").json()["blocked"] is None
    client.post("/api/kit/session/stop")


def test_stop_button_never_500s(client):
    def boom():
        raise RuntimeError("RTDE gone")
    backend = client.app.state.robot_bridge.backend
    backend.stop = boom
    r = client.post("/api/kit/robot/stop")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and "RTDE gone" in body["error"]
    assert body["state"]["latched"] == "estop"      # latched even though the backend failed


def test_connect_endpoint_and_mat_cleared_event(client):
    cleared = []
    r = client.post("/api/kit/robot/connect")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["state"]["connected"] is True
    assert client.post("/api/kit/event", json={"type": "mat_cleared"}).status_code == 200


def test_robot_endpoints_503_without_a_bridge(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from hub.kit_study.router import build_kit_router
    from hub.kit_study.session import KitSession

    bus = MessageBus()
    db = Database(tmp_path / "hri.db")
    ctrl = RecordingController(bus, db, tmp_path / "recordings")
    app = FastAPI()
    app.include_router(build_kit_router(KitSession(bus, db, ctrl), bus, bridge=None))
    with TestClient(app) as c:
        for path in ("/api/kit/robot/state", "/api/kit/supply/state"):
            assert c.get(path).status_code == 503
        for path in ("/api/kit/robot/home", "/api/kit/robot/stop", "/api/kit/robot/connect",
                     "/api/kit/robot/open_gripper"):
            assert c.post(path).status_code == 503
        assert c.post("/api/kit/supply/profile", json={"lookahead": 1}).status_code == 503


def test_profile_requires_session(client):
    assert client.post("/api/kit/supply/profile", json={"lookahead": 1}).status_code == 409


def test_robot_mode_fails_closed_without_taught_calibration(tmp_path):
    missing = tmp_path / "missing.yaml"
    cfg = load_mode("robot", overrides={"robot": {"calibration": str(missing)}})
    with pytest.raises(RobotError):
        build_backend(cfg)


def test_ursim_mode_opts_into_example_calibration(tmp_path, caplog):
    missing = tmp_path / "missing.yaml"
    cfg = load_mode("ursim", overrides={"robot": {"calibration": str(missing)}})
    with caplog.at_level(logging.WARNING):
        backend = build_backend(cfg)  # must not attempt any network connection
    assert isinstance(backend, URBackend)
    assert any("EXAMPLE calibration" in r.message for r in caplog.records)


def test_relative_calibration_path_resolves_against_hri_monitor_root():
    cfg = load_mode("robot")
    resolved = resolve_calibration_path(cfg)
    assert resolved.is_absolute()
    assert resolved == HRI_MONITOR_ROOT / "hub" / "kit_study" / "configs" / "calibration.yaml"


# --------------------------------------------------------------------- robot.gripper.kind
def test_build_backend_default_gripper_is_tool_do():
    """No robot.gripper key (or kind: tool_do) -> URBackend builds its own ToolDOGripper,
    bound to its own RTDE IO interface so reconnects keep working."""
    from hub.kit_study.robotd.gripper import ToolDOGripper
    cfg = load_mode("ursim")
    backend = build_backend(cfg)
    assert isinstance(backend.gripper, ToolDOGripper)
    assert backend.gripper.do == 0


def test_build_backend_onrobot_modbus_gripper():
    from hub.kit_study.robotd.gripper import OnRobotModbusGripper
    cfg = load_mode("ursim", overrides={"robot": {
        "gripper": {"kind": "onrobot_modbus", "ip": "192.168.1.1", "port": 5020,
                    "unit_id": 65, "force_n": 12.0, "open_width_mm": 80.0,
                    "close_width_mm": 20.0, "settle_s": 0.5}}})
    backend = build_backend(cfg)
    assert isinstance(backend.gripper, OnRobotModbusGripper)
    assert backend.gripper.ip == "192.168.1.1"
    assert backend.gripper.port == 5020
    assert backend.gripper.force_n == 12.0
    assert backend.gripper.open_width_mm == 80.0
    assert backend.gripper.close_width_mm == 20.0
    assert backend.gripper.settle_s == 0.5


def test_build_backend_onrobot_urcap_gripper_defaults_ip_to_robot_ip():
    from hub.kit_study.robotd.gripper import OnRobotURCapGripper
    cfg = load_mode("ursim", overrides={"robot": {
        "gripper": {"kind": "onrobot_urcap", "force_n": 15.0, "open_width_mm": 90.0,
                    "close_width_mm": 18.0, "timeout_s": 5.0}}})
    backend = build_backend(cfg)
    assert isinstance(backend.gripper, OnRobotURCapGripper)
    assert backend.gripper.ip == "127.0.0.1"   # ursim.yaml robot.ip — same controller, no box
    assert backend.gripper.force_n == 15.0
    assert backend.gripper.open_width_mm == 90.0
    assert backend.gripper.close_width_mm == 18.0
    assert backend.gripper.timeout_s == 5.0


def test_build_backend_onrobot_urcap_gripper_ip_override():
    from hub.kit_study.robotd.gripper import OnRobotURCapGripper
    cfg = load_mode("ursim", overrides={"robot": {
        "gripper": {"kind": "onrobot_urcap", "ip": "10.9.8.7"}}})
    backend = build_backend(cfg)
    assert isinstance(backend.gripper, OnRobotURCapGripper)
    assert backend.gripper.ip == "10.9.8.7"


def test_build_backend_unknown_gripper_kind_raises():
    cfg = load_mode("ursim", overrides={"robot": {"gripper": {"kind": "bogus"}}})
    with pytest.raises(ValueError, match="unknown gripper kind"):
        build_backend(cfg)
