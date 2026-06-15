"""V4L2 camera enumeration via sysfs (dependency-free)."""
import os
import re

_SYSFS = "/sys/class/video4linux"
_VIDEO_RE = re.compile(r"^video(\d+)$")


def list_cameras_from_sysfs(root: str = _SYSFS) -> list[dict]:
    cams = []
    if not os.path.isdir(root):
        return cams
    for entry in os.listdir(root):
        m = _VIDEO_RE.match(entry)
        if not m:
            continue
        idx = int(m.group(1))
        name_path = os.path.join(root, entry, "name")
        try:
            name = open(name_path).read().strip()
        except OSError:
            name = entry
        cams.append({"index": idx, "path": f"/dev/video{idx}", "name": name})
    return sorted(cams, key=lambda c: c["index"])


def list_cameras() -> list[dict]:
    return list_cameras_from_sysfs()
