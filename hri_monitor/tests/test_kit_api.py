import pytest
from fastapi.testclient import TestClient

from hub.bus import MessageBus
from hub.experiments.controller import RecordingController
from hub.experiments.db import Database
from hub.server import create_app


class FakeManager:
    config = {"sensors": {}}
    def statuses(self):
        return {}


@pytest.fixture
def client(tmp_path):
    bus = MessageBus()
    db = Database(tmp_path / "hri.db")
    ctrl = RecordingController(bus, db, tmp_path / "recordings")
    app = create_app(bus, FakeManager(), ui_dir=None, config_path=tmp_path / "c.yaml",
                     experiments={"db": db, "controller": ctrl})
    with TestClient(app) as c:
        yield c, bus
    kit = app.state.kit_session
    if kit.status() is not None:
        kit.stop()


def test_session_lifecycle(client):
    c, _ = client
    r = c.post("/api/kit/session/start",
               json={"participant_code": "P01", "condition": "C0"})
    assert r.status_code == 200 and r.json()["condition"] == "C0"
    assert c.post("/api/kit/session/start",
                  json={"participant_code": "P01", "condition": "C1"}).status_code == 409
    st = c.get("/api/kit/state").json()
    assert st["session"]["task"]["phase"] == "running"
    assert c.post("/api/kit/session/stop").status_code == 200
    assert c.get("/api/kit/state").json()["session"] is None


def test_events(client):
    c, bus = client
    seen = []
    bus.subscribe("wizard.reposition", lambda m: seen.append(m))
    c.post("/api/kit/session/start", json={"participant_code": "P01", "condition": "C0"})
    before = c.get("/api/kit/state").json()["session"]["task"]["step_index"]
    assert c.post("/api/kit/event", json={"type": "part_placed"}).status_code == 200
    after = c.get("/api/kit/state").json()["session"]["task"]["step_index"]
    assert after == before + 1
    assert c.post("/api/kit/event",
                  json={"type": "reposition", "payload": {"slot": "L"}}).status_code == 200
    assert seen and seen[0]["data"]["slot"] == "L"
    c.post("/api/kit/session/stop")


def test_event_without_session_409(client):
    c, _ = client
    assert c.post("/api/kit/event", json={"type": "part_placed"}).status_code == 409


def test_bad_condition_400(client):
    c, _ = client
    r = c.post("/api/kit/session/start",
               json={"participant_code": "P01", "condition": "C9"})
    assert r.status_code == 400
