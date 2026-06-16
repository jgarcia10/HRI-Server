"""Analysis REST: options, compare (per-feature), plot (svg/pdf), values export."""
import csv
import io
import math

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from .compare import compare
from .features import FEATURES
from .plots import figure_bytes


def _json_safe(o):
    """Replace NaN/Inf with None so results stay JSON-compliant. Statistical tests
    on degenerate data (e.g. ties → undefined effect size / shapiro p) emit NaN,
    which the JSON encoder rejects."""
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_json_safe(v) for v in o]
    return o

_ALL_SIGNALS = ["shimmer.gsr", "shimmer.ppg", "ppg.hr", "ppg.hrv", "rgb.blink",
                "thermal.forehead", "thermal.left_cheek", "thermal.right_cheek", "thermal.nose"]


def _present_signals(db, experiment_id):
    seen = set()
    for r in db.recordings_for_conditions(
            experiment_id, [c["id"] for c in (db.get_experiment(experiment_id) or {"conditions": []})["conditions"]]):
        try:
            with open(r["csv_path"]) as f:
                next(f, None)
                for line in f:
                    parts = line.split(",")
                    if len(parts) >= 2:
                        seen.add(parts[1])
                    if len(seen) >= len(_ALL_SIGNALS):
                        break
        except OSError:
            continue
    return [s for s in _ALL_SIGNALS if s in seen]


def _cond_names(db, experiment_id):
    exp = db.get_experiment(experiment_id)
    return {c["id"]: c["name"] for c in exp["conditions"]} if exp else {}


class CompareIn(BaseModel):
    experiment_id: int
    condition_ids: list[int]
    signal: str
    features: list[str]
    unit: str = "participant"


def build_analysis_router(db) -> APIRouter:
    r = APIRouter()

    @r.get("/api/experiments/{exp_id}/analysis/options")
    def options(exp_id: int):
        exp = db.get_experiment(exp_id)
        if not exp:
            return JSONResponse({"error": "not found"}, status_code=404)
        return {"signals": _present_signals(db, exp_id), "features": FEATURES,
                "conditions": [{"id": c["id"], "name": c["name"]} for c in exp["conditions"]]}

    @r.post("/api/analysis/compare")
    def do_compare(body: CompareIn):
        names = _cond_names(db, body.experiment_id)
        results = []
        for feat in body.features:
            try:
                results.append(compare(db, body.experiment_id, body.condition_ids,
                                       body.signal, feat, body.unit, names))
            except Exception as e:  # noqa: BLE001
                results.append({"ok": False, "feature": feat, "signal": body.signal,
                                "reason": f"could not compute: {e}"})
        return JSONResponse(_json_safe({"results": results}))

    @r.get("/api/analysis/plot")
    def plot(experiment_id: int, signal: str, feature: str, format: str = "svg",
             unit: str = "participant", condition_ids: list[int] = Query(default=[])):
        names = _cond_names(db, experiment_id)
        res = compare(db, experiment_id, condition_ids, signal, feature, unit, names)
        order = [names.get(cid, str(cid)) for cid in condition_ids]
        title = f"{feature} of {signal} by condition"
        data = figure_bytes(res.get("values", []), order, title, f"{signal} · {feature}", format)
        media = "image/svg+xml" if format == "svg" else "application/pdf"
        return Response(data, media_type=media,
                        headers={"Content-Disposition": f'attachment; filename="analysis_{signal}_{feature}.{format}"'})

    @r.post("/api/analysis/export.csv")
    def export_values(body: CompareIn):
        names = _cond_names(db, body.experiment_id)
        buf = io.StringIO(); w = csv.writer(buf)
        w.writerow(["signal", "feature", "condition", "subject", "value"])
        for feat in body.features:
            res = compare(db, body.experiment_id, body.condition_ids, body.signal, feat, body.unit, names)
            for v in res.get("values", []):
                w.writerow([body.signal, feat, v["condition"], v["subject"], v["value"]])
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="analysis_values.csv"'})

    return r
