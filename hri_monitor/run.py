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


def load_dotenv(path: Path) -> None:
    """Export KEY=VALUE lines from a local, git-ignored `.env` (OpenAI key etc.).
    Existing environment variables win; no dependency on python-dotenv."""
    import os
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="HRI Monitor")
    parser.add_argument("--no-browser", action="store_true", help="do not open the dashboard")
    parser.add_argument("--mode", choices=["sim", "robot", "ursim"], default="sim",
                        help="robot backend: sim (no hardware), robot (UR5 via ur_rtde), "
                             "or ursim (URSim rehearsal, example calibration)")
    parser.add_argument("--robot-ip", default=None, help="override the UR5 IP from the mode file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    config = load_config(ROOT / "config.yaml")
    bus = MessageBus()
    manager = SensorManager(bus, config)
    manager.start_all()
    from hub.experiments.controller import RecordingController
    from hub.experiments.db import Database
    data_dir = ROOT / config.get("data_dir", "data")
    exp_db = Database(data_dir / "hri.db")
    rec_ctrl = RecordingController(bus, exp_db, data_dir / "recordings")
    experiments = {"db": exp_db, "controller": rec_ctrl}
    from hub.kit_study.runtime import load_mode
    kit_mode = load_mode(args.mode, {"robot": {"ip": args.robot_ip}} if args.robot_ip else None)
    app = create_app(bus, manager, ui_dir=ROOT / "ui_dist",
                     config_path=ROOT / "config.yaml", experiments=experiments, kit_mode=kit_mode)

    host, port = config["server"]["host"], config["server"]["port"]
    browser_timer = None
    if config["server"]["open_browser"] and not args.no_browser:
        browser_timer = threading.Timer(1.5, webbrowser.open, args=[f"http://{host}:{port}"])
        browser_timer.start()
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    finally:
        if browser_timer is not None:
            browser_timer.cancel()
        manager.stop_all()


if __name__ == "__main__":
    main()
