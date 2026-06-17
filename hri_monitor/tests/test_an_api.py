from fastapi import FastAPI
from fastapi.testclient import TestClient

from hub.analysis.router import build_analysis_router
from hub.experiments.db import Database


def setup(tmp_path):
    db = Database(tmp_path / "hri.db")
    exp = db.create_experiment("S", "")
    db.set_conditions(exp, ["A", "B"])
    conds = [c["id"] for c in db.get_experiment(exp)["conditions"]]
    app = FastAPI(); app.include_router(build_analysis_router(db))
    return db, exp, conds, TestClient(app)


def _rec(db, tmp_path, exp, pid_code, cid, signal, values, idx):
    pid = db.create_participant(exp, pid_code) if isinstance(pid_code, str) else pid_code
    sess = db.create_session(exp, pid)
    p = tmp_path / f"r{idx}.csv"
    p.write_text("t_offset,signal,value\n" + "".join(f"{i*0.1},{signal},{v}\n" for i, v in enumerate(values)))
    db.create_recording(sess, cid, str(p))
    return pid


def test_options_lists_present_signals(tmp_path):
    db, exp, conds, client = setup(tmp_path)
    _rec(db, tmp_path, exp, "P1", conds[0], "shimmer.gsr", [2, 3, 4], 1)
    opt = client.get(f"/api/experiments/{exp}/analysis/options").json()
    assert "shimmer.gsr" in opt["signals"]
    assert "mean" in opt["features"]
    assert any(c["name"] == "A" for c in opt["conditions"])


def test_compare_returns_one_result_per_feature(tmp_path):
    db, exp, conds, client = setup(tmp_path)
    for code, base in [("P1", 0), ("P2", 1), ("P3", 2)]:
        pid = _rec(db, tmp_path, exp, code, conds[0], "shimmer.gsr", [2 + base, 3 + base, 4 + base], f"{code}a")
        _rec(db, tmp_path, exp, pid, conds[1], "shimmer.gsr", [5 + base, 6 + base, 7 + base], f"{code}b")
    r = client.post("/api/analysis/compare", json={
        "experiment_id": exp, "condition_ids": conds, "signals": ["shimmer.gsr"],
        "features": ["mean", "sd"], "unit": "participant"})
    body = r.json()
    assert len(body["results"]) == 2
    assert {res["feature"] for res in body["results"]} == {"mean", "sd"}
    assert body["results"][0]["design"] == "paired"


def test_plot_endpoint_svg(tmp_path):
    db, exp, conds, client = setup(tmp_path)
    for code, base in [("P1", 0), ("P2", 1), ("P3", 2)]:
        pid = _rec(db, tmp_path, exp, code, conds[0], "shimmer.gsr", [2 + base, 3 + base], f"{code}a")
        _rec(db, tmp_path, exp, pid, conds[1], "shimmer.gsr", [5 + base, 6 + base], f"{code}b")
    r = client.get(f"/api/analysis/plot", params={
        "experiment_id": exp, "condition_ids": conds, "signal": "shimmer.gsr",
        "feature": "mean", "unit": "participant", "format": "svg"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg")


def test_export_csv_has_rows(tmp_path):
    db, exp, conds, client = setup(tmp_path)
    for code, base in [("P1", 0), ("P2", 1), ("P3", 2)]:
        pid = _rec(db, tmp_path, exp, code, conds[0], "shimmer.gsr", [2 + base, 3 + base, 4 + base], f"{code}a")
        _rec(db, tmp_path, exp, pid, conds[1], "shimmer.gsr", [5 + base, 6 + base, 7 + base], f"{code}b")
    r = client.post("/api/analysis/export.csv", json={
        "experiment_id": exp, "condition_ids": conds, "signals": ["shimmer.gsr"],
        "features": ["mean"], "unit": "participant"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    assert lines[0] == "signal,feature,condition,subject,value"
    assert len(lines) > 1  # header + at least one value row


def test_plot_rejects_bad_format(tmp_path):
    db, exp, conds, client = setup(tmp_path)
    r = client.get("/api/analysis/plot", params={
        "experiment_id": exp, "condition_ids": conds, "signal": "shimmer.gsr",
        "feature": "mean", "unit": "participant", "format": "png"})
    assert r.status_code == 400


def test_compare_multi_signal_and_feature(tmp_path):
    db, exp, conds, client = setup(tmp_path)
    for code, base in [("P1", 0), ("P2", 1), ("P3", 2)]:
        pid = None
        for cidx, cid in enumerate(conds):
            pid = db.create_participant(exp, code) if cidx == 0 else pid
            sess = db.create_session(exp, pid)
            p = tmp_path / f"{code}_{cid}.csv"
            p.write_text("t_offset,signal,value\n" + "".join(
                f"{i*0.1},shimmer.gsr,{2+base+cidx*3+i}\n{i*0.1},ppg.hr,{60+base+cidx*2+i}\n" for i in range(3)))
            db.create_recording(sess, cid, str(p))
    r = client.post("/api/analysis/compare", json={
        "experiment_id": exp, "condition_ids": conds, "signals": ["shimmer.gsr", "ppg.hr"],
        "features": ["mean", "auc_per_min"], "unit": "participant", "normalize": "range"})
    results = r.json()["results"]
    assert len(results) == 4  # 2 signals × 2 features
    tags = {(x["signal"], x["feature"]) for x in results}
    assert tags == {("shimmer.gsr", "mean"), ("shimmer.gsr", "auc_per_min"),
                    ("ppg.hr", "mean"), ("ppg.hr", "auc_per_min")}
    assert all(x.get("normalize") == "range" for x in results)


def test_options_lists_normalizations(tmp_path):
    db, exp, conds, client = setup(tmp_path)
    opt = client.get(f"/api/experiments/{exp}/analysis/options").json()
    assert opt["normalizations"] == ["none", "range", "zscore"]
    assert "auc_per_min" in opt["features"]


def test_plot_with_normalize_param(tmp_path):
    db, exp, conds, client = setup(tmp_path)
    for code, base in [("P1", 0), ("P2", 1), ("P3", 2)]:
        pid = db.create_participant(exp, code)
        for cid in conds:
            sess = db.create_session(exp, pid)
            p = tmp_path / f"{code}_{cid}.csv"
            p.write_text("t_offset,signal,value\n" + "".join(f"{i*0.1},shimmer.gsr,{2+base+cid+i}\n" for i in range(3)))
            db.create_recording(sess, cid, str(p))
    r = client.get("/api/analysis/plot", params={
        "experiment_id": exp, "condition_ids": conds, "signal": "shimmer.gsr",
        "feature": "mean", "unit": "participant", "format": "svg", "normalize": "range"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg")
