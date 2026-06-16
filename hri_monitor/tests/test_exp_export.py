import io
import zipfile

from hub.experiments.db import Database
from hub.experiments.export import session_zip_bytes


def test_session_zip_contains_csvs_and_manifest(tmp_path):
    db = Database(tmp_path / "hri.db")
    exp = db.create_experiment("S", "")
    db.set_conditions(exp, ["Baseline"])
    cond = db.get_experiment(exp)["conditions"][0]["id"]
    part = db.create_participant(exp, "P01", "")
    sess = db.create_session(exp, part)
    csv1 = tmp_path / "1.csv"
    csv1.write_text("t_offset,signal,value\n0.0,shimmer.gsr,4.2\n")
    rec = db.create_recording(sess, cond, str(csv1))
    db.finalize_recording(rec, sample_count=1)
    blob = session_zip_bytes(db, sess)
    z = zipfile.ZipFile(io.BytesIO(blob))
    names = z.namelist()
    assert "session.json" in names
    assert "manifest.csv" in names
    assert any(n.endswith(".csv") and "recording" in n for n in names)
    assert b"shimmer.gsr" in z.read([n for n in names if n.startswith("recordings/")][0])
