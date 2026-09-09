"""HTTP API for the kit study: session lifecycle + wizard events."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .session import KitSession


class SessionStartIn(BaseModel):
    participant_code: str
    condition: str
    block: str = "orders_f1.yaml"
    profile: dict | None = None


class KitEventIn(BaseModel):
    type: str
    payload: dict = {}


class ProfileIn(BaseModel):
    lookahead: int | None = None
    side: str | None = None
    pace: str | None = None
    announce: bool | None = None


def build_kit_router(session: KitSession, bus, bridge=None) -> APIRouter:
    r = APIRouter()

    @r.post("/api/kit/session/start")
    def start(body: SessionStartIn):
        try:
            return session.start(body.participant_code, body.condition, body.block, body.profile)
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
        if body.type == "request_part":
            bus.publish("wizard.request_part", {})
            return {"ok": True}
        if body.type == "slot_cleared":
            bus.publish("wizard.slot_cleared", {"slot": body.payload.get("slot")})
            return {"ok": True}
        if body.type == "mat_cleared":
            bus.publish("wizard.mat_cleared", {})
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

    def _no_robot():
        return JSONResponse({"detail": "no robot bridge configured"}, status_code=503)

    @r.get("/api/kit/robot/state")
    def robot_state():
        if bridge is None:
            return _no_robot()
        return bridge.state()

    @r.post("/api/kit/robot/connect")
    def robot_connect():
        if bridge is None:
            return _no_robot()
        st = bridge.connect()
        return {"ok": bool(st.get("connected")), "state": st}

    @r.post("/api/kit/robot/home")
    def robot_home():
        if bridge is None:
            return _no_robot()
        job_id = bridge.submit("home")
        return {"ok": job_id is not None, "job_id": job_id}

    @r.post("/api/kit/robot/open_gripper")
    def robot_open():
        if bridge is None:
            return _no_robot()
        job_id = bridge.submit("open_gripper")
        return {"ok": job_id is not None, "job_id": job_id}

    @r.post("/api/kit/robot/stop")
    def robot_stop():
        # The STOP button must never fail: a backend that raises still leaves the bridge
        # latched, and the wizard gets the error in the body rather than a 500.
        if bridge is None:
            return _no_robot()
        error = None
        try:
            bridge.estop()
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        try:
            st = bridge.state()
        except Exception:
            st = None
        return {"ok": error is None, "error": error, "state": st}

    @r.get("/api/kit/supply/state")
    def supply_state():
        if bridge is None:
            return _no_robot()
        return session.supply.status() if session.supply else {}

    @r.post("/api/kit/supply/profile")
    def supply_profile(body: ProfileIn):
        if bridge is None:
            return _no_robot()
        if session.supply is None:
            return JSONResponse({"detail": "no active session"}, status_code=409)
        try:
            session.supply.set_profile(**{k: v for k, v in body.model_dump().items() if v is not None})
        except ValueError as e:
            return JSONResponse({"detail": str(e)}, status_code=400)
        return session.supply.status()

    return r
