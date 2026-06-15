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
