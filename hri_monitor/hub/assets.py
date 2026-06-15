"""Resolve sensor asset files (thermal calibration XML, dlib models) against
known base dirs. These assets often live at the repo root (one level above
hri_monitor/) and are not copied into the package, so relative config paths
must be searched rather than assumed cwd-relative."""
import glob
import os

# .../hri_monitor/hub/assets.py -> hri_monitor/
HRI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(HRI_ROOT)


def _base_dirs():
    # cwd first (explicit user intent), then the package root, then the repo root.
    return [os.getcwd(), HRI_ROOT, REPO_ROOT]


def resolve_asset(path):
    """Absolute path to `path` if found as-is, absolute, or under a known base
    dir; else None."""
    if not path:
        return None
    if os.path.isabs(path):
        return path if os.path.exists(path) else None
    for base in _base_dirs():
        cand = os.path.join(base, path)
        if os.path.exists(cand):
            return os.path.abspath(cand)
    return None


def list_thermal_xml():
    """Discover Optris calibration XML files (named <serial>.xml) near the project."""
    found = {}
    for base in (HRI_ROOT, REPO_ROOT):
        for p in glob.glob(os.path.join(base, "*.xml")):
            found.setdefault(os.path.basename(p), os.path.abspath(p))
    return sorted(found)
