import copy
from pathlib import Path

import yaml

DEFAULTS = {
    "server": {"host": "127.0.0.1", "port": 8000, "open_browser": True},
    "data_dir": "data",
    "sensors": {
        "shimmer": {"enabled": True, "simulate": True, "mac": None, "sampling_rate": 200},
        "thermal": {"enabled": True, "simulate": True, "xml": None},
        "rgb": {"enabled": True, "simulate": True, "index": 0, "width": 640, "height": 480, "fps": 30},
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path | str = "config.yaml") -> dict:
    path = Path(path)
    user = {}
    if path.exists():
        user = yaml.safe_load(path.read_text()) or {}
    return _merge(DEFAULTS, user)
