from hub.analysis.compare import gather

class FakeDB:
    """Minimal db stand-in: recordings keyed by (condition_id) -> [(participant_id, csv_path)]."""
    def __init__(self, rows):
        self._rows = rows  # list of dict(participant_id, condition_id, csv_path)
    def recordings_for_conditions(self, experiment_id, condition_ids):
        return [r for r in self._rows if r["condition_id"] in condition_ids]


def make_csv(tmp_path, name, signal, values):
    p = tmp_path / name
    p.write_text("t_offset,signal,value\n" + "".join(f"{i*0.1},{signal},{v}\n" for i, v in enumerate(values)))
    return str(p)


def test_per_participant_aggregation_and_paired(tmp_path):
    # P1 and P2 each have one recording in cond 1 and cond 2 → paired
    rows = [
        {"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "a", "shimmer.gsr", [2, 4])},
        {"participant_id": 2, "condition_id": 1, "csv_path": make_csv(tmp_path, "b", "shimmer.gsr", [3, 5])},
        {"participant_id": 1, "condition_id": 2, "csv_path": make_csv(tmp_path, "c", "shimmer.gsr", [5, 7])},
        {"participant_id": 2, "condition_id": 2, "csv_path": make_csv(tmp_path, "d", "shimmer.gsr", [6, 8])},
    ]
    g = gather(FakeDB(rows), experiment_id=1, condition_ids=[1, 2],
               signal="shimmer.gsr", feature="mean", unit="participant")
    assert g["paired"] is True
    # one value per (participant, condition); P1 cond1 mean of [2,4]=3
    assert {(r["subject"], r["condition_id"]): r["value"] for r in g["rows"]}[(1, 1)] == 3.0
    assert sorted(g["counts"].values()) == [2, 2]   # 2 subjects per condition


def test_unpaired_when_participants_differ(tmp_path):
    rows = [
        {"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "a", "shimmer.gsr", [2])},
        {"participant_id": 2, "condition_id": 2, "csv_path": make_csv(tmp_path, "b", "shimmer.gsr", [4])},
    ]
    g = gather(FakeDB(rows), 1, [1, 2], "shimmer.gsr", "mean", "participant")
    assert g["paired"] is False


def test_per_recording_unit_keeps_each_recording(tmp_path):
    rows = [
        {"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "a", "shimmer.gsr", [2])},
        {"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "b", "shimmer.gsr", [4])},
    ]
    g = gather(FakeDB(rows), 1, [1], "shimmer.gsr", "mean", "recording")
    assert g["counts"][1] == 2 and g["paired"] is False


def test_per_participant_averages_multiple_recordings(tmp_path):
    # P1 has TWO recordings in cond 1 → the row value must be their mean
    rows = [
        {"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "a", "shimmer.gsr", [2])},   # mean 2
        {"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "b", "shimmer.gsr", [6])},   # mean 6
    ]
    g = gather(FakeDB(rows), 1, [1], "shimmer.gsr", "mean", "participant")
    # one aggregated row for P1 in cond1, value = mean(2, 6) = 4.0
    assert len(g["rows"]) == 1
    assert g["rows"][0]["subject"] == 1 and g["rows"][0]["value"] == 4.0
    assert g["counts"][1] == 1


def test_complete_case_filtering_and_unpaired(tmp_path):
    # P1,P2 in cond1; only P1 in cond2 → participant sets differ → unpaired,
    # and cond2 keeps only its present participant.
    rows = [
        {"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "a", "shimmer.gsr", [2])},
        {"participant_id": 2, "condition_id": 1, "csv_path": make_csv(tmp_path, "b", "shimmer.gsr", [3])},
        {"participant_id": 1, "condition_id": 2, "csv_path": make_csv(tmp_path, "c", "shimmer.gsr", [5])},
    ]
    g = gather(FakeDB(rows), 1, [1, 2], "shimmer.gsr", "mean", "participant")
    assert g["paired"] is False
    assert g["counts"][1] == 2 and g["counts"][2] == 1


def test_missing_csv_path_is_skipped(tmp_path):
    # one valid recording + one pointing at a nonexistent file → the bad one is skipped, no raise
    good = make_csv(tmp_path, "good", "shimmer.gsr", [2, 4])
    rows = [
        {"participant_id": 1, "condition_id": 1, "csv_path": good},
        {"participant_id": 2, "condition_id": 1, "csv_path": str(tmp_path / "does_not_exist.csv")},
    ]
    g = gather(FakeDB(rows), 1, [1], "shimmer.gsr", "mean", "recording")
    assert g["counts"][1] == 1  # only the readable recording contributed
