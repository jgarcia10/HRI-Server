import pytest

from hub.experiments.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "hri.db")


def test_create_experiment_with_conditions_and_labels(db):
    exp = db.create_experiment("Trust Study", "desc")
    db.set_conditions(exp, ["Baseline", "Transparent", "Opaque"])
    db.set_marker_labels(exp, ["Stimulus onset", "Robot error"])
    got = db.get_experiment(exp)
    assert got["name"] == "Trust Study"
    assert [c["name"] for c in got["conditions"]] == ["Baseline", "Transparent", "Opaque"]
    assert [c["order_index"] for c in got["conditions"]] == [0, 1, 2]
    assert sorted(l["label"] for l in got["marker_labels"]) == ["Robot error", "Stimulus onset"]


def test_participant_code_unique_per_experiment(db):
    exp = db.create_experiment("S", "")
    db.create_participant(exp, "P01", "")
    with pytest.raises(Exception):
        db.create_participant(exp, "P01", "")
    exp2 = db.create_experiment("S2", "")
    assert db.create_participant(exp2, "P01", "") > 0


def test_session_recording_marker_flow(db):
    exp = db.create_experiment("S", "")
    db.set_conditions(exp, ["Baseline"])
    cond = db.get_experiment(exp)["conditions"][0]["id"]
    part = db.create_participant(exp, "P01", "")
    sess = db.create_session(exp, part)
    rec = db.create_recording(sess, cond, "data/recordings/1.csv")
    db.add_marker(rec, 1.5, "Robot error", "button")
    db.finalize_recording(rec, sample_count=10, status="completed")
    detail = db.get_recording(rec)
    assert detail["status"] == "completed" and detail["sample_count"] == 10
    assert detail["markers"][0]["label"] == "Robot error"
    assert detail["markers"][0]["t_offset"] == 1.5


def test_delete_experiment_cascades(db):
    exp = db.create_experiment("S", "")
    db.set_conditions(exp, ["Baseline"])
    cond = db.get_experiment(exp)["conditions"][0]["id"]
    part = db.create_participant(exp, "P01", "")
    sess = db.create_session(exp, part)
    rec = db.create_recording(sess, cond, "x.csv")
    db.delete_experiment(exp)
    assert db.get_experiment(exp) is None
    assert db.get_recording(rec) is None


def test_active_recordings_reconciled_to_interrupted(db):
    exp = db.create_experiment("S", "")
    db.set_conditions(exp, ["Baseline"])
    cond = db.get_experiment(exp)["conditions"][0]["id"]
    part = db.create_participant(exp, "P01", "")
    sess = db.create_session(exp, part)
    rec = db.create_recording(sess, cond, "x.csv")  # left 'active'
    assert db.get_recording(rec)["status"] == "active"
    n = db.reconcile_active_recordings()
    assert n == 1
    assert db.get_recording(rec)["status"] == "interrupted"


def test_delete_experiment_unlinks_csv_files(db, tmp_path):
    exp = db.create_experiment("S", "")
    db.set_conditions(exp, ["Baseline"])
    cond = db.get_experiment(exp)["conditions"][0]["id"]
    part = db.create_participant(exp, "P01", "")
    sess = db.create_session(exp, part)
    csv = tmp_path / "rec1.csv"
    csv.write_text("t_offset,signal,value\n0.0,shimmer.gsr,4.2\n")
    db.create_recording(sess, cond, str(csv))
    assert csv.exists()
    db.delete_experiment(exp)
    assert not csv.exists()   # CSV removed, not orphaned


def test_delete_participant_unlinks_csv_files(db, tmp_path):
    exp = db.create_experiment("S", "")
    db.set_conditions(exp, ["Baseline"])
    cond = db.get_experiment(exp)["conditions"][0]["id"]
    part = db.create_participant(exp, "P01", "")
    sess = db.create_session(exp, part)
    csv = tmp_path / "rec2.csv"
    csv.write_text("t_offset,signal,value\n")
    db.create_recording(sess, cond, str(csv))
    db.delete_participant(part)
    assert not csv.exists()
