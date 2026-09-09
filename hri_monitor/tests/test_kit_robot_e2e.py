"""Full-stack robot-in-the-loop: HTTP session -> engine -> supply -> sim robot backend
-> recorder CSV. Drives an entire F1 block (37 parts across 6 orders), waiting for each
part to actually be staged by the robot bridge before "placing" it, and checks that the
mock ANIMA perception pipeline also produced a signal.
"""
import csv
import time

from fastapi.testclient import TestClient

from hub.bus import MessageBus
from hub.experiments.controller import RecordingController
from hub.experiments.db import Database
from hub.server import create_app

# orders_f1.yaml: O1=4, O2=5, O3=9, O4=4, O5=9, O6=6 parts -> 37 total (verified against the YAML).
TOTAL_PARTS = 37


class FakeManager:
    config = {"sensors": {}}
    def statuses(self):
        return {}


FAST = {"robot": {"backend": "sim", "timing": {"home": 0.002, "pick": 0.002, "place": 0.002,
                                               "open_gripper": 0.002, "noise_std": 0.0}},
        "supply": {"lookahead": 2, "side": "C", "pace": "normal", "announce": False}}


def test_full_block_robot_supplies_every_part(tmp_path):
    bus = MessageBus()
    db = Database(tmp_path / "hri.db")
    ctrl = RecordingController(bus, db, tmp_path / "recordings")
    app = create_app(bus, FakeManager(), ui_dir=None, config_path=tmp_path / "c.yaml",
                     experiments={"db": db, "controller": ctrl}, kit_mode=FAST)
    staged = []
    bus.subscribe("robot.part_staged", lambda m: staged.append(m["data"]["part_id"]))
    try:
        with TestClient(app) as c:
            rec = c.post("/api/kit/session/start", json={"participant_code": "P99", "condition": "C1"}).json()
            for _ in range(6):
                task = c.get("/api/kit/state").json()["session"]["task"]
                for step in range(task["n_parts"]):
                    # wait until the part for this step is staged before "placing" it
                    t0 = time.time()
                    cur = None
                    while time.time() - t0 < 5.0:
                        sup = c.get("/api/kit/supply/state").json()
                        cur = c.get("/api/kit/state").json()["session"]["task"]["current_part"]["id"]
                        if cur in sup["staged"].values():
                            break
                        time.sleep(0.01)
                    assert cur in sup["staged"].values(), f"part {cur} never staged"
                    assert c.post("/api/kit/event", json={"type": "part_placed"}).status_code == 200
                task = c.get("/api/kit/state").json()["session"]["task"]
                if task["phase"] == "between_orders":
                    c.post("/api/kit/event", json={"type": "next_order"})
            assert c.get("/api/kit/state").json()["session"]["task"]["phase"] == "done"
            c.post("/api/kit/event", json={"type": "speech", "payload": {"text": "great, thanks"}})
            time.sleep(1.5)  # let the mock ANIMA perception job (queued on wizard.speech) finish
            c.post("/api/kit/session/stop")
        assert len(staged) == TOTAL_PARTS and len(set(staged)) == TOTAL_PARTS
        info = db.get_recording(rec["recording_id"])
        with open(info["csv_path"]) as f:
            signals = [row["signal"] for row in csv.DictReader(f)]
        assert signals.count("robot.part_staged") == TOTAL_PARTS
        assert "robot.skill_duration_s" in signals and "task.part_placed" in signals
        assert "anima.intensity" in signals            # mock perception recorded
    finally:
        app.state.robot_bridge.stop()
        app.state.anima_llm.stop()
