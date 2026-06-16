"""Build a session export .zip: each recording's CSV + session.json + manifest.csv."""
import io
import json
import os
import zipfile


def session_zip_bytes(db, session_id) -> bytes:
    with db._conn() as c:
        sess = c.execute("SELECT * FROM session WHERE id=?", (session_id,)).fetchone()
        if sess is None:
            raise ValueError(f"session {session_id} not found")
        exp = db.get_experiment(sess["experiment_id"])
        part = c.execute("SELECT * FROM participant WHERE id=?", (sess["participant_id"],)).fetchone()
    recordings = db.list_recordings(session_id)
    cond_name = {cond["id"]: cond["name"] for cond in exp["conditions"]}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        manifest = ["recording_id,condition,started_at,sample_count,csv"]
        for rec in recordings:
            arc = f"recordings/recording_{rec['id']}.csv"
            if rec["csv_path"] and os.path.exists(rec["csv_path"]):
                z.write(rec["csv_path"], arc)
            manifest.append(
                f"{rec['id']},{cond_name.get(rec['condition_id'], '')},{rec['started_at']},{rec['sample_count']},{arc}")
        z.writestr("manifest.csv", "\n".join(manifest) + "\n")
        meta = {
            "experiment": {"id": exp["id"], "name": exp["name"], "description": exp["description"]},
            "participant": {"code": part["code"], "notes": part["notes"]} if part else None,
            "conditions": exp["conditions"],
            "recordings": [
                {"id": rec["id"], "condition": cond_name.get(rec["condition_id"], ""),
                 "started_at": rec["started_at"], "stopped_at": rec["stopped_at"],
                 "sample_count": rec["sample_count"], "status": rec["status"],
                 "markers": db.get_recording(rec["id"])["markers"]}
                for rec in recordings
            ],
        }
        z.writestr("session.json", json.dumps(meta, indent=2))
    return buf.getvalue()
