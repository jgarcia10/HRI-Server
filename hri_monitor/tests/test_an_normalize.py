import numpy as np

from hub.analysis.normalize import params, participant_transforms


class FakeDB:
    def __init__(self, rows):
        self._rows = rows  # [{participant_id, condition_id, csv_path}]
    def recordings_for_experiment(self, experiment_id):
        return list(self._rows)


def make_csv(tmp_path, name, signal, values):
    p = tmp_path / name
    p.write_text("t_offset,signal,value\n" + "".join(f"{i*0.1},{signal},{v}\n" for i, v in enumerate(values)))
    return str(p)


def test_params_range():
    a, b = params([2.0, 4.0, 6.0], "range")
    assert a == 2.0 and b == 4.0  # min=2, max-min=4


def test_params_zscore():
    a, b = params([2.0, 4.0, 6.0], "zscore")
    assert a == 4.0 and abs(b - np.std([2, 4, 6])) < 1e-9


def test_params_constant_signal_has_unit_divisor():
    a, b = params([3.0, 3.0, 3.0], "range")
    assert b == 1.0  # max-min == 0 → guarded to 1.0
    az, bz = params([3.0, 3.0, 3.0], "zscore")
    assert bz == 1.0


def test_participant_transforms_use_all_conditions(tmp_path):
    # P1 has values 0..10 spread across TWO conditions → range params from BOTH
    rows = [
        {"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "a", "shimmer.gsr", [0.0, 10.0])},
        {"participant_id": 1, "condition_id": 2, "csv_path": make_csv(tmp_path, "b", "shimmer.gsr", [5.0])},
    ]
    tf = participant_transforms(FakeDB(rows), 1, "shimmer.gsr", "range")
    assert set(tf) == {1}
    # range over P1's full data is [0,10] → 10 maps to 1.0, 0 maps to 0.0, 5 maps to 0.5
    out = tf[1](np.array([0.0, 5.0, 10.0]))
    assert np.allclose(out, [0.0, 0.5, 1.0])


def test_participant_transforms_none_method_empty(tmp_path):
    rows = [{"participant_id": 1, "condition_id": 1, "csv_path": make_csv(tmp_path, "a", "shimmer.gsr", [1.0])}]
    assert participant_transforms(FakeDB(rows), 1, "shimmer.gsr", "none") == {}
