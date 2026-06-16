from fastapi.testclient import TestClient
from fastapi import FastAPI

from hub.bus import MessageBus
from hub.experiments.controller import RecordingController
from hub.experiments.db import Database
from hub.experiments.router import build_router


def make_client(tmp_path):
    db = Database(tmp_path / "hri.db")
    bus = MessageBus()
    ctrl = RecordingController(bus, db, tmp_path / "recordings")
    app = FastAPI()
    app.include_router(build_router(db, ctrl))
    return db, ctrl, TestClient(app)


def test_experiment_crud_and_conditions(tmp_path):
    _, _, client = make_client(tmp_path)
    r = client.post("/api/experiments", json={"name": "Trust", "description": "d"})
    exp = r.json()["id"]
    client.put(f"/api/experiments/{exp}/conditions", json={"conditions": ["Baseline", "Transparent"]})
    client.put(f"/api/experiments/{exp}/marker-labels", json={"labels": ["Robot error"]})
    got = client.get(f"/api/experiments/{exp}").json()
    assert got["name"] == "Trust"
    assert [c["name"] for c in got["conditions"]] == ["Baseline", "Transparent"]
    assert got["marker_labels"][0]["label"] == "Robot error"


def test_participants(tmp_path):
    _, _, client = make_client(tmp_path)
    exp = client.post("/api/experiments", json={"name": "S"}).json()["id"]
    p = client.post(f"/api/experiments/{exp}/participants", json={"code": "P01", "notes": ""})
    assert p.status_code == 200
    lst = client.get(f"/api/experiments/{exp}/participants").json()
    assert lst[0]["code"] == "P01"


def test_recording_lifecycle_and_export(tmp_path):
    db, _, client = make_client(tmp_path)
    exp = client.post("/api/experiments", json={"name": "S"}).json()["id"]
    client.put(f"/api/experiments/{exp}/conditions", json={"conditions": ["Baseline"]})
    cond = client.get(f"/api/experiments/{exp}").json()["conditions"][0]["id"]
    part = client.post(f"/api/experiments/{exp}/participants", json={"code": "P01"}).json()["id"]
    started = client.post("/api/recordings/start",
                          json={"experiment_id": exp, "participant_id": part, "condition_id": cond})
    rec = started.json()["recording_id"]
    assert client.get("/api/recordings/active").json()["recording_id"] == rec
    client.post(f"/api/recordings/{rec}/marker", json={"label": "Robot error", "source": "button"})
    client.post(f"/api/recordings/{rec}/stop")
    assert client.get("/api/recordings/active").json() is None
    exp_csv = client.get(f"/api/recordings/{rec}/export.csv")
    assert exp_csv.status_code == 200 and "t_offset" in exp_csv.text
    client.post("/api/recordings/start", json={"experiment_id": exp, "participant_id": part, "condition_id": cond})
    dup = client.post("/api/recordings/start", json={"experiment_id": exp, "participant_id": part, "condition_id": cond})
    assert dup.status_code == 409
    client.post(f"/api/recordings/{client.get('/api/recordings/active').json()['recording_id']}/stop")


def test_active_status_shape(tmp_path):
    db, ctrl, client = make_client(tmp_path)
    exp = client.post("/api/experiments", json={"name": "S"}).json()["id"]
    client.put(f"/api/experiments/{exp}/conditions", json={"conditions": ["Baseline"]})
    cond = client.get(f"/api/experiments/{exp}").json()["conditions"][0]["id"]
    part = client.post(f"/api/experiments/{exp}/participants", json={"code": "P01"}).json()["id"]
    rec = client.post("/api/recordings/start",
                      json={"experiment_id": exp, "participant_id": part, "condition_id": cond}).json()["recording_id"]
    st = client.get("/api/recordings/active").json()
    assert st["recording_id"] == rec
    assert st["condition"] == "Baseline"
    assert "elapsed" in st and "sample_count" in st and "markers" in st
    client.post(f"/api/recordings/{rec}/stop")
