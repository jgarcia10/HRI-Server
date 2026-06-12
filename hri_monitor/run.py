#!/usr/bin/env python3
"""HRI Monitor — single entry point. Starts sensors and the web hub, then
opens the dashboard in the default browser."""
import argparse
import logging
import threading
import webbrowser
from pathlib import Path

import uvicorn

from hub.bus import MessageBus
from hub.config import load_config
from hub.sensors.manager import SensorManager
from hub.server import create_app

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="HRI Monitor")
    parser.add_argument("--no-browser", action="store_true", help="do not open the dashboard")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    config = load_config(ROOT / "config.yaml")
    bus = MessageBus()
    manager = SensorManager(bus, config)
    manager.start_all()
    app = create_app(bus, manager, ui_dir=ROOT / "ui_dist")

    host, port = config["server"]["host"], config["server"]["port"]
    if config["server"]["open_browser"] and not args.no_browser:
        threading.Timer(1.5, webbrowser.open, args=[f"http://{host}:{port}"]).start()
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    finally:
        manager.stop_all()


if __name__ == "__main__":
    main()
