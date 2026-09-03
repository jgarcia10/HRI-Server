"""HTTP API for the kit study: session lifecycle + wizard events."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .session import KitSession


class SessionStartIn(BaseModel):
    participant_code: str
    condition: str
    block: str = "orders_f1.yaml"


class KitEventIn(BaseModel):
    type: str
    payload: dict = {}


def build_kit_router(session: KitSession, bus) -> APIRouter:
    r = APIRouter()

    @r.post("/api/kit/session/start")
    def start(body: SessionStartIn):
        try:
            return session.start(body.participant_code, body.condition, body.block)
        except RuntimeError as e:
            return JSONResponse({"detail": str(e)}, status_code=409)
        except (ValueError, FileNotFoundError) as e:
            return JSONResponse({"detail": str(e)}, status_code=400)

    @r.post("/api/kit/session/stop")
    def stop():
        return session.stop() or {"ok": True}

    @r.get("/api/kit/state")
    def state():
        return {"session": session.status()}

    @r.post("/api/kit/event")
    def event(body: KitEventIn):
        if body.type == "reposition":
            bus.publish("wizard.reposition", {"slot": str(body.payload.get("slot", "?"))})
            return {"ok": True}
        if body.type == "speech":
            bus.publish("wizard.speech", {"text": str(body.payload.get("text", ""))})
            return {"ok": True}
        if session.engine is None:
            return JSONResponse({"detail": "no active session"}, status_code=409)
        if body.type == "part_placed":
            session.engine.mark_part_placed()
            return {"ok": True}
        if body.type == "next_order":
            session.engine.next_order()
            return {"ok": True}
        return JSONResponse({"detail": f"unknown event type {body.type}"}, status_code=400)

    return r
