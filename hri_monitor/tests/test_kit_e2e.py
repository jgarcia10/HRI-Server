"""Full-stack (minus browser): HTTP session → engine → recorder CSV + markers."""
import csv
import time

from fastapi.testclient import TestClient

from hub.bus import MessageBus
from hub.experiments.controller import RecordingController
from hub.experiments.db import Database
from hub.server import create_app


class FakeManager:
    config = {"sensors": {}}
    def statuses(self):
        return {}


def test_block_over_http(tmp_path):
    bus = MessageBus()
    db = Database(tmp_path / "hri.db")
    ctrl = RecordingController(bus, db, tmp_path / "recordings")
    app = create_app(bus, FakeManager(), ui_dir=None, config_path=tmp_path / "c.yaml",
                     experiments={"db": db, "controller": ctrl})
    with TestClient(app) as c:
        rec = c.post("/api/kit/session/start",
                     json={"participant_code": "P99", "condition": "C1"}).json()
        for _ in range(6):                                   # six orders
            state = c.get("/api/kit/state").json()["session"]["task"]
            for _ in range(state["n_parts"]):
                assert c.post("/api/kit/event", json={"type": "part_placed"}).status_code < 300
            state = c.get("/api/kit/state").json()["session"]["task"]
            if state["phase"] == "between_orders":
                assert c.post("/api/kit/event", json={"type": "next_order"}).status_code < 300
        assert c.get("/api/kit/state").json()["session"]["task"]["phase"] == "done"
        time.sleep(1.2)                                       # ≥1 recorder flush
        out = c.post("/api/kit/session/stop").json()
    info = db.get_recording(rec["recording_id"])
    assert info["status"] == "completed"
    labels = [m["label"] for m in info["markers"]]
    assert sum(l.startswith("order_started") for l in labels) == 6
    assert any(l.startswith("block_completed") for l in labels)
    with open(info["csv_path"]) as f:
        signals = [row["signal"] for row in csv.DictReader(f)]
    assert signals.count("task.part_placed") == 37            # 4+5+9+4+9+6 parts
    assert "task.order_index" in signals
