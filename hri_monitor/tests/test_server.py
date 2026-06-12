from fastapi.testclient import TestClient

from hub.bus import MessageBus
from hub.server import create_app


class FakeManager:
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
