"""FastAPI routes for experiments/participants/recordings/export."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from .export import session_zip_bytes


class ExperimentIn(BaseModel):
    name: str
    description: str = ""

class NamesIn(BaseModel):
    conditions: list[str] = []

class LabelsIn(BaseModel):
    labels: list[str] = []

class ParticipantIn(BaseModel):
    code: str
    notes: str = ""

class StartIn(BaseModel):
    condition_id: int
    experiment_id: int | None = None
    participant_id: int | None = None
    session_id: int | None = None

class MarkerIn(BaseModel):
    label: str
    source: str = "button"


def build_router(db, controller) -> APIRouter:
    r = APIRouter()

    @r.get("/api/experiments")
    def list_experiments():
        return db.list_experiments()

    @r.post("/api/experiments")
    def create_experiment(body: ExperimentIn):
        return {"id": db.create_experiment(body.name, body.description)}

    @r.get("/api/experiments/{exp_id}")
    def get_experiment(exp_id: int):
        e = db.get_experiment(exp_id)
        return e if e else JSONResponse({"error": "not found"}, status_code=404)

    @r.patch("/api/experiments/{exp_id}")
    def update_experiment(exp_id: int, body: ExperimentIn):
        db.update_experiment(exp_id, body.name, body.description)
        return {"ok": True}

    @r.delete("/api/experiments/{exp_id}")
    def delete_experiment(exp_id: int):
        db.delete_experiment(exp_id)
        return {"ok": True}

    @r.put("/api/experiments/{exp_id}/conditions")
    def set_conditions(exp_id: int, body: NamesIn):
        db.set_conditions(exp_id, body.conditions)
        return {"ok": True}

    @r.put("/api/experiments/{exp_id}/marker-labels")
    def set_marker_labels(exp_id: int, body: LabelsIn):
        db.set_marker_labels(exp_id, body.labels)
        return {"ok": True}

    @r.get("/api/experiments/{exp_id}/participants")
    def list_participants(exp_id: int):
        return db.list_participants(exp_id)

    @r.post("/api/experiments/{exp_id}/participants")
    def create_participant(exp_id: int, body: ParticipantIn):
        return {"id": db.create_participant(exp_id, body.code, body.notes)}

    @r.patch("/api/participants/{pid}")
    def update_participant(pid: int, body: ParticipantIn):
        db.update_participant(pid, body.code, body.notes)
        return {"ok": True}

    @r.delete("/api/participants/{pid}")
    def delete_participant(pid: int):
        db.delete_participant(pid)
        return {"ok": True}

    @r.get("/api/experiments/{exp_id}/sessions")
    def list_sessions(exp_id: int):
        out = []
        for s in db.list_sessions(exp_id):
            s["recordings"] = db.list_recordings(s["id"])
            out.append(s)
        return out

    @r.post("/api/recordings/start")
    def start_recording(body: StartIn):
        try:
            return controller.start(condition_id=body.condition_id,
                                    experiment_id=body.experiment_id,
                                    participant_id=body.participant_id,
                                    session_id=body.session_id)
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=409)

    @r.post("/api/recordings/{rec_id}/marker")
    def add_marker(rec_id: int, body: MarkerIn):
        try:
            controller.marker(body.label, body.source)
            return {"ok": True}
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=409)

    @r.post("/api/recordings/{rec_id}/stop")
    def stop_recording(rec_id: int):
        return controller.stop() or {"ok": True}

    @r.get("/api/recordings/active")
    def active_recording():
        return controller.status()

    @r.get("/api/recordings/{rec_id}")
    def get_recording(rec_id: int):
        rec = db.get_recording(rec_id)
        return rec if rec else JSONResponse({"error": "not found"}, status_code=404)

    @r.get("/api/recordings/{rec_id}/export.csv")
    def export_csv(rec_id: int):
        rec = db.get_recording(rec_id)
        if not rec or not rec["csv_path"]:
            return JSONResponse({"error": "not found"}, status_code=404)
        with open(rec["csv_path"]) as f:
            data = f.read()
        return Response(data, media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="recording_{rec_id}.csv"'})

    @r.get("/api/sessions/{session_id}/export.zip")
    def export_zip(session_id: int):
        blob = session_zip_bytes(db, session_id)
        return Response(blob, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="session_{session_id}.zip"'})

    return r
