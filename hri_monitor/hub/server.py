import asyncio
import threading
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import assets, bluetooth, cameras
from .config import save_config
from .frames import FrameStore

# Numeric topics forwarded to the dashboard. Frame topics carry numpy arrays
# and are served via MJPEG instead — never JSON.
STREAM_TOPICS = {
    "shimmer.gsr", "shimmer.ppg", "thermal.temps", "rgb.blink",
    "ppg.hr", "ppg.hrv", "model.estimates",
}
WS_FLUSH_SECONDS = 0.1  # dashboard update rate (~10 Hz)
MJPEG_FPS = 15


def create_app(bus, manager, ui_dir=None, config_path="config.yaml") -> FastAPI:
    app = FastAPI(title="HRI Monitor")
    frames = FrameStore(bus, {"thermal": "thermal.frame", "rgb": "rgb.frame"})
    app.state.frames = frames

    @app.get("/api/status")
    def status():
        return {"devices": manager.statuses()}

    SAMPLING_RATES = [128, 200, 256, 512]

    @app.get("/api/devices")
    def devices():
        cfg = getattr(manager, "config", {}).get("sensors", {})
        st = manager.statuses()
        out = {}
        for name, c in cfg.items():
            out[name] = {"config": c, "status": st.get(name, "disabled")}
        return {
            "devices": out,
            "options": {
                "cameras": cameras.list_cameras(),
                "sampling_rates": SAMPLING_RATES,
                "serial_ports": bluetooth.list_serial_ports(),
                "thermal_xml": assets.list_thermal_xml(),
            },
        }

    class DeviceConfig(BaseModel):
        simulate: bool | None = None
        index: int | None = None
        width: int | None = None
        height: int | None = None
        fps: int | None = None
        xml: str | None = None
        mac: str | None = None
        sampling_rate: int | None = None
        channel: int | None = None
        port: str | None = None

    @app.post("/api/devices/{name}/config")
    def set_device_config(name: str, body: DeviceConfig):
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        # An empty-string port means "use Bluetooth socket, not a serial port":
        # apply it explicitly since the None-strip above would otherwise drop it.
        if body.port == "":
            updates["port"] = None
        manager.reconfigure(name, updates)
        save_config(config_path, manager.config)
        return {"ok": True, "config": manager.config["sensors"].get(name)}

    @app.post("/api/devices/{name}/{action}")
    def device_action(name: str, action: str):
        if action == "restart":
            manager.restart(name)
        elif action == "connect":
            manager.connect(name)
        elif action == "disconnect":
            manager.disconnect(name)
        else:
            return JSONResponse({"error": f"unknown action '{action}'"}, status_code=400)
        return {"ok": True}

    class BtScan(BaseModel):
        seconds: int = 8

    @app.post("/api/bluetooth/scan")
    def bt_scan(body: BtScan):
        return {"devices": bluetooth.scan(seconds=body.seconds)}

    class BtPair(BaseModel):
        mac: str
        pin: str = "1234"

    @app.post("/api/bluetooth/pair")
    def bt_pair(body: BtPair):
        return bluetooth.pair(body.mac, body.pin)

    class BtBind(BaseModel):
        mac: str
        channel: int = 1

    @app.post("/api/bluetooth/bind")
    def bt_bind(body: BtBind):
        """Bind /dev/rfcommN for the Shimmer and, on success, point the shimmer
        device at that serial port + switch it to real — one click, no terminal."""
        result = bluetooth.bind_rfcomm(body.mac, body.channel)
        if result.get("ok") and "shimmer" in manager.config.get("sensors", {}):
            manager.reconfigure("shimmer", {"port": result["port"], "simulate": False})
            save_config(config_path, manager.config)
        return result

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
