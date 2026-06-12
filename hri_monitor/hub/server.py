import asyncio
import threading
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .frames import FrameStore

# Numeric topics forwarded to the dashboard. Frame topics carry numpy arrays
# and are served via MJPEG instead — never JSON.
STREAM_TOPICS = {
    "shimmer.gsr", "shimmer.ppg", "thermal.temps", "rgb.blink",
    "ppg.hr", "ppg.hrv", "model.estimates",
}
WS_FLUSH_SECONDS = 0.1  # dashboard update rate (~10 Hz)
MJPEG_FPS = 15


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
        except (WebSocketDisconnect, RuntimeError):
            # RuntimeError covers "send after close" under real uvicorn
            pass
        finally:
            bus.unsubscribe("*", on_message)

    @app.get("/stream/{feed}")
    def stream(feed: str):
        if not frames.has(feed):
            return JSONResponse({"error": f"unknown feed '{feed}'"}, status_code=404)

        def gen():
            while True:
                jpg = frames.jpeg(feed)
                if jpg is not None:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
                time.sleep(1.0 / MJPEG_FPS)

        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    if ui_dir and Path(ui_dir).is_dir():
        app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    return app
