import time

import pytest
from fastapi.testclient import TestClient

from hub.bus import MessageBus
from hub.experiments.controller import RecordingController
from hub.experiments.db import Database
from hub.kit_study.runtime import build_backend, load_mode
from hub.server import create_app


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


def test_request_part_event_and_estop(client):
    client.post("/api/kit/session/start",
                json={"participant_code": "P02", "condition": "C1", "profile": {"lookahead": 0}})
    time.sleep(0.1)
    assert client.get("/api/kit/supply/state").json()["staged"] == {}
    assert client.post("/api/kit/event", json={"type": "request_part"}).status_code == 200
    assert wait(client, lambda s: len(s["session"]["supply"]["staged"]) == 1)
    assert client.post("/api/kit/robot/stop").status_code == 200
    assert client.get("/api/kit/robot/state").json()["queue"] == 0
    client.post("/api/kit/session/stop")


def test_profile_requires_session(client):
    assert client.post("/api/kit/supply/profile", json={"lookahead": 1}).status_code == 409
