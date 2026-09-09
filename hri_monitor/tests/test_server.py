import time

from fastapi.testclient import TestClient

from hub.bus import MessageBus
from hub.server import create_app


class FakeManager:
    config = {"sensors": {}}

    def statuses(self):
        return {"shimmer": "connected"}


def make_client():
    bus = MessageBus()
    client = TestClient(create_app(bus, FakeManager()))
    return bus, client


def test_status_endpoint_reports_devices():
    _, client = make_client()
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {"devices": {"shimmer": "connected"}}


def test_ws_sends_hello_then_streams_published_samples():
    bus, client = make_client()
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["devices"] == {"shimmer": "connected"}
        bus.publish("shimmer.gsr", {"value": 4.2})
        update = ws.receive_json()
        assert update["type"] == "update"
        assert update["items"]["shimmer.gsr"]["data"] == {"value": 4.2}
        assert update["devices"] == {"shimmer": "connected"}


def test_unknown_stream_feed_returns_404():
    _, client = make_client()
    response = client.get("/stream/nope")
    assert response.status_code == 404


def test_static_ui_served_when_dir_exists(tmp_path):
    (tmp_path / "index.html").write_text("<html><body>hri</body></html>")
    bus = MessageBus()
    client = TestClient(create_app(bus, FakeManager(), ui_dir=tmp_path))
    response = client.get("/")
    assert response.status_code == 200
    assert "hri" in response.text


def test_devices_endpoint_lists_config_and_options(monkeypatch):
    import hub.server as srv
    monkeypatch.setattr(srv.cameras, "list_cameras", lambda: [{"index": 0, "path": "/dev/video0", "name": "Cam"}])

    class M:
        config = {"sensors": {"rgb": {"simulate": True, "index": 0, "width": 640, "height": 480, "fps": 30}}}
        def statuses(self): return {"rgb": "connected"}
    from hub.bus import MessageBus
    from fastapi.testclient import TestClient
    client = TestClient(srv.create_app(MessageBus(), M()))
    r = client.get("/api/devices")
    assert r.status_code == 200
    body = r.json()
    assert body["devices"]["rgb"]["status"] == "connected"
    assert body["devices"]["rgb"]["config"]["index"] == 0
    assert body["options"]["cameras"][0]["name"] == "Cam"


def test_device_config_post_persists_and_reconfigures(tmp_path, monkeypatch):
    import hub.server as srv
    calls = {}

    class M:
        config = {"sensors": {"rgb": {"simulate": True, "index": 0, "width": 640, "height": 480, "fps": 30}}}
        def statuses(self): return {"rgb": "connected"}
        def reconfigure(self, name, updates): calls["reconf"] = (name, updates)
    saved = {}
    monkeypatch.setattr(srv, "save_config", lambda p, c: saved.setdefault("c", c))
    from hub.bus import MessageBus
    from fastapi.testclient import TestClient
    client = TestClient(srv.create_app(MessageBus(), M(), config_path=tmp_path / "config.yaml"))
    r = client.post("/api/devices/rgb/config", json={"index": 7, "simulate": False})
    assert r.status_code == 200
    assert calls["reconf"][0] == "rgb" and calls["reconf"][1]["index"] == 7
    assert "c" in saved


def test_bluetooth_scan_endpoint(monkeypatch):
    import hub.server as srv
    monkeypatch.setattr(srv.bluetooth, "scan", lambda seconds=8: [{"mac": "AA", "name": "Shimmer3", "paired": False}])
    from hub.bus import MessageBus
    from fastapi.testclient import TestClient
    client = TestClient(srv.create_app(MessageBus(), FakeManager()))
    r = client.post("/api/bluetooth/scan", json={"seconds": 2})
    assert r.status_code == 200 and r.json()["devices"][0]["name"] == "Shimmer3"


# --------------------------------------------------------------------------------------------
# I2: shutdown must never leave the robot/RTDE connection/LLM worker dangling on process exit.
# --------------------------------------------------------------------------------------------

def _kit_app(tmp_path, robot_timing=None):
    from hub.experiments.controller import RecordingController
    from hub.experiments.db import Database
    bus = MessageBus()
    db = Database(tmp_path / "hri.db")
    ctrl = RecordingController(bus, db, tmp_path / "recordings")
    kit_mode = {
        "robot": {"backend": "sim", "timing": {"home": 0.002, "pick": 0.002, "place": 0.002,
                                               "open_gripper": robot_timing or 0.002, "noise_std": 0.0}},
        "supply": {"lookahead": 1, "side": "C", "pace": "normal", "announce": False},
    }
    app = create_app(bus, FakeManager(), ui_dir=None, config_path=tmp_path / "c.yaml",
                     experiments={"db": db, "controller": ctrl}, kit_mode=kit_mode)
    return app


def test_shutdown_stops_robot_bridge_and_anima_llm_when_idle(tmp_path):
    app = _kit_app(tmp_path)
    bridge, anima_llm = app.state.robot_bridge, app.state.anima_llm
    session = app.state.kit_session
    calls = []
    orig_estop, orig_bridge_stop, orig_llm_stop = bridge.estop, bridge.stop, anima_llm.stop
    orig_session_stop = session.stop
    session.stop = lambda: (calls.append("session.stop"), orig_session_stop())[-1]
    bridge.estop = lambda: (calls.append("estop"), orig_estop())[-1]
    bridge.stop = lambda: (calls.append("bridge.stop"), orig_bridge_stop())[-1]
    anima_llm.stop = lambda: (calls.append("anima_llm.stop"), orig_llm_stop())[-1]

    with TestClient(app):
        pass  # nothing running: the bridge sits idle

    assert "estop" not in calls  # nothing was mid-motion, so no estop needed
    # session first (it unsubscribes supply so nothing re-submits), then the bridge, then LLM
    assert calls == ["session.stop", "bridge.stop", "anima_llm.stop"]


def test_shutdown_stops_a_running_kit_session(tmp_path):
    """A Ctrl-C mid-block must close the recording, not leave it dangling."""
    app = _kit_app(tmp_path)
    session, ctrl = app.state.kit_session, app.state.recording_controller
    with TestClient(app) as client:
        r = client.post("/api/kit/session/start",
                        json={"participant_code": "P99", "condition": "C0"})
        assert r.status_code == 200, r.text
        assert session.status() is not None
        assert ctrl.status() is not None
    assert session.status() is None      # torn down by the lifespan shutdown
    assert ctrl.status() is None         # ... and the recording was closed


def test_shutdown_estops_when_a_skill_is_in_flight(tmp_path):
    app = _kit_app(tmp_path, robot_timing=1.0)  # open_gripper takes 1s: still running at shutdown
    bridge = app.state.robot_bridge
    calls = []
    orig_estop, orig_bridge_stop = bridge.estop, bridge.stop
    bridge.estop = lambda: (calls.append("estop"), orig_estop())[-1]
    bridge.stop = lambda: (calls.append("bridge.stop"), orig_bridge_stop())[-1]

    with TestClient(app):
        bridge.submit("open_gripper")
        t0 = time.time()
        while not bridge.state()["busy"] and time.time() - t0 < 2.0:
            time.sleep(0.01)
        assert bridge.state()["busy"], "skill never started"
        # exit the `with` here -> lifespan shutdown fires while the skill is still running

    assert calls == ["estop", "bridge.stop"]


def test_shutdown_is_a_noop_without_kit_study(tmp_path):
    # No `experiments=` -> no robot_bridge/anima_llm on app.state; shutdown must not blow up.
    bus = MessageBus()
    with TestClient(create_app(bus, FakeManager())):
        pass
