import asyncio
import threading

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .frames import FrameStore

# Numeric topics forwarded to the dashboard. Frame topics carry numpy arrays
# and are served via MJPEG instead — never JSON.
STREAM_TOPICS = {
    "shimmer.gsr", "shimmer.ppg", "thermal.temps", "rgb.blink",
    "ppg.hr", "ppg.hrv", "model.estimates",
}
WS_FLUSH_SECONDS = 0.1  # dashboard update rate (~10 Hz)


def create_app(bus, manager, ui_dir=None) -> FastAPI:
    app = FastAPI(title="HRI Monitor")
    frames = FrameStore(bus, {"thermal": "thermal.frame", "rgb": "rgb.frame"})
    app.state.frames = frames

    @app.get("/api/status")
    def status():
        return {"devices": manager.statuses()}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        pending: dict = {}
        lock = threading.Lock()

        def on_message(message):
            if message["topic"] in STREAM_TOPICS:
                with lock:
                    pending[message["topic"]] = {"ts": message["ts"], "data": message["data"]}

        bus.subscribe("*", on_message)
        try:
            await ws.send_json({"type": "hello", "devices": manager.statuses()})
            while True:
                await asyncio.sleep(WS_FLUSH_SECONDS)
                with lock:
                    items = dict(pending)
                    pending.clear()
                if items:
                    await ws.send_json({"type": "update", "items": items,
                                        "devices": manager.statuses()})
        except WebSocketDisconnect:
            pass
        finally:
            bus.unsubscribe("*", on_message)

    return app
