"""Post-block questionnaires: opened on session stop, stored in the DB, block the next start
until answered or skipped, exported in the Physio-HRC CSV layout."""
import csv
import io

import pytest
from fastapi.testclient import TestClient

from hub.bus import MessageBus
from hub.experiments.controller import RecordingController
from hub.experiments.db import Database
from hub.kit_study.questionnaires import INSTRUMENTS, score, to_csv, validate
from hub.server import create_app


class FakeManager:
    config = {"sensors": {}}

    def statuses(self):
        return {}


TLX = {"mental_demand": 65, "physical_demand": 40, "temporal_demand": 40, "performance": 45,
       "effort": 45, "frustration": 40}
TRUST = {"reliability": 6, "competence": 6, "predictability": 5, "transparency": 6}


@pytest.fixture
def client(tmp_path):
    bus = MessageBus()
    db = Database(tmp_path / "hri.db")
    ctrl = RecordingController(bus, db, tmp_path / "rec")
    app = create_app(bus, FakeManager(), ui_dir=None, config_path=tmp_path / "c.yaml",
                     experiments={"db": db, "controller": ctrl},
                     kit_mode={"robot": {"backend": "sim", "timing": {"home": 0.002, "pick": 0.002,
                                                                      "place": 0.002, "open_gripper": 0.002,
                                                                      "noise_std": 0.0}}})
    events = []
    bus.subscribe("kit.questionnaire", lambda m: events.append(m["data"]))
    with TestClient(app) as c:
        c.events = events
        c.db = db
        yield c
        app.state.robot_bridge.stop()


def run_block(c, code="P01", condition="C0"):
    assert c.post("/api/kit/session/start",
                  json={"participant_code": code, "condition": condition}).status_code == 200
    assert c.post("/api/kit/session/stop").status_code == 200


def test_validate_and_score_match_dataset_conventions():
    clean = validate("nasa_tlx", TLX)
    assert score("nasa_tlx", clean) == 45.83
    assert score("trust_hrts", validate("trust_hrts", TRUST)) == 5.75
    with pytest.raises(ValueError):
        validate("nasa_tlx", {**TLX, "effort": 101})
    with pytest.raises(ValueError):
        validate("trust_hrts", {k: v for k, v in TRUST.items() if k != "competence"})
    with pytest.raises(ValueError):
        validate("sus", {})


def test_stop_opens_questionnaires_and_blocks_next_start(client):
    assert client.get("/api/kit/questionnaire").json()["status"] == "none"
    run_block(client)
    st = client.get("/api/kit/questionnaire").json()
    assert st["status"] == "pending" and st["next"] == "nasa_tlx"
    assert st["participant"] == "P01" and st["condition"] == "C0"
    assert set(st["instruments"]) == {"nasa_tlx", "trust_hrts"}
    r = client.post("/api/kit/session/start", json={"participant_code": "P01", "condition": "C1"})
    assert r.status_code == 409 and "questionnaires pending" in r.json()["detail"]
    assert client.events and client.events[-1]["status"] == "pending"


def test_answers_are_stored_and_next_block_can_start(client):
    run_block(client)
    r = client.post("/api/kit/questionnaire", json={"instrument": "nasa_tlx", "answers": TLX})
    assert r.status_code == 200 and r.json()["next"] == "trust_hrts"
    # same instrument twice is refused; the other is still expected
    assert client.post("/api/kit/questionnaire", json={"instrument": "nasa_tlx", "answers": TLX}).status_code == 409
    r = client.post("/api/kit/questionnaire", json={"instrument": "trust_hrts", "answers": TRUST})
    assert r.status_code == 200 and r.json()["status"] == "done" and r.json()["outcome"] == "completed"
    rows = client.db.list_questionnaires()
    assert [(x["instrument"], x["score"], x["participant_code"], x["condition_name"]) for x in rows] == \
        [("nasa_tlx", 45.83, "P01", "C0"), ("trust_hrts", 5.75, "P01", "C0")]
    assert rows[0]["session_id"] == rows[1]["session_id"] and rows[0]["recording_id"] is not None
    assert client.post("/api/kit/session/start", json={"participant_code": "P01", "condition": "C1"}).status_code == 200
    client.post("/api/kit/session/stop")


def test_bad_answers_are_rejected(client):
    run_block(client)
    r = client.post("/api/kit/questionnaire", json={"instrument": "nasa_tlx", "answers": {**TLX, "effort": 250}})
    assert r.status_code == 400
    assert client.get("/api/kit/questionnaire").json()["status"] == "pending"


def test_skip_records_the_gap_and_unblocks(client):
    run_block(client)
    client.post("/api/kit/questionnaire", json={"instrument": "nasa_tlx", "answers": TLX})
    r = client.post("/api/kit/questionnaire/skip", json={"reason": "participant declined"})
    assert r.json()["status"] == "done" and r.json()["outcome"] == "skipped"
    rows = client.db.list_questionnaires(instrument="trust_hrts")
    assert rows[0]["answers"] == {"skipped": "participant declined"} and rows[0]["score"] is None
    assert client.post("/api/kit/session/start", json={"participant_code": "P01", "condition": "C1"}).status_code == 200
    client.post("/api/kit/session/stop")


def test_csv_export_has_dataset_layout(client):
    run_block(client, "P02", "C1")
    client.post("/api/kit/questionnaire", json={"instrument": "nasa_tlx", "answers": TLX})
    client.post("/api/kit/questionnaire/skip")
    r = client.get("/api/kit/questionnaires/nasa_tlx.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert list(rows[0].keys()) == ["participant_id", "condition", "mental_demand", "physical_demand",
                                    "temporal_demand", "performance", "effort", "frustration", "overall_score"]
    assert rows[0]["participant_id"] == "P02" and rows[0]["condition"] == "C1" and rows[0]["overall_score"] == "45.83"
    trust = list(csv.DictReader(io.StringIO(client.get("/api/kit/questionnaires/trust_hrts.csv").text)))
    assert trust == []          # skipped rows are not exported as data
    assert client.get("/api/kit/questionnaires/sus.csv").status_code == 404
    assert to_csv("trust_hrts", []).splitlines()[0] == \
        "participant_id,condition,reliability,competence,predictability,transparency,overall_trust"
    assert INSTRUMENTS["nasa_tlx"]["items"][3]["low"] == "Perfect"   # performance runs Perfect → Failure
