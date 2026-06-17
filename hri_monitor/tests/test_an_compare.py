import pytest

from hub.analysis.compare import run_test


def rows(pairs):
    # pairs: list of (subject, condition_id, value)
    return [{"subject": s, "condition_id": c, "value": v} for s, c, v in pairs]


def test_paired_two_conditions_significant():
    g = {"paired": True, "counts": {1: 5, 2: 5},
         "rows": rows([(i, 1, v) for i, v in enumerate([2, 3, 4, 3, 2])]
                      + [(i, 2, v) for i, v in enumerate([4, 5, 6, 5, 4])])}
    res = run_test(g, [1, 2], cond_names={1: "A", 2: "B"})
    assert res["ok"] is True
    assert res["test"] in ("paired t-test", "Wilcoxon signed-rank")
    assert res["design"] == "paired"
    assert res["p"] < 0.05
    assert res["effect_size"]["name"] and res["effect_size"]["magnitude"] in ("small", "medium", "large")
    assert "A" in res["interpretation"]


def test_unpaired_two_conditions():
    g = {"paired": False, "counts": {1: 5, 2: 5},
         "rows": rows([(i, 1, v) for i, v in enumerate([2, 3, 4, 3, 2])]
                      + [(10 + i, 2, v) for i, v in enumerate([5, 6, 7, 6, 5])])}
    res = run_test(g, [1, 2], cond_names={1: "A", 2: "B"})
    assert res["design"] == "unpaired"
    assert res["test"] in ("independent t-test", "Mann-Whitney U")


def test_three_conditions_paired_has_posthoc():
    base = [4.0, 4.2, 3.8, 4.1, 3.9, 4.0]
    g = {"paired": True, "counts": {1: 6, 2: 6, 3: 6},
         "rows": rows([(i, 1, v) for i, v in enumerate(base)]
                      + [(i, 2, v + 1.0) for i, v in enumerate(base)]
                      + [(i, 3, v + 2.0) for i, v in enumerate(base)])}
    res = run_test(g, [1, 2, 3], cond_names={1: "A", 2: "B", 3: "C"})
    assert res["test"] in ("repeated-measures ANOVA", "Friedman")
    assert res["ok"] and res["p"] < 0.05
    assert len(res["posthoc"]) == 3  # A-B, A-C, B-C


def test_insufficient_data_guard():
    g = {"paired": True, "counts": {1: 2, 2: 5}, "rows": rows([(0, 1, 1), (1, 1, 2)])}
    res = run_test(g, [1, 2], cond_names={1: "A", 2: "B"})
    assert res["ok"] is False and "insufficient" in res["reason"].lower()


def test_unpaired_three_conditions_anova():
    # three independent groups, well separated, ~normal → one-way ANOVA
    g = {"paired": False, "counts": {1: 6, 2: 6, 3: 6},
         "rows": rows([(i, 1, v) for i, v in enumerate([4.0, 4.2, 3.8, 4.1, 3.9, 4.0])]
                      + [(10 + i, 2, v) for i, v in enumerate([5.0, 5.2, 4.8, 5.1, 4.9, 5.0])]
                      + [(20 + i, 3, v) for i, v in enumerate([6.0, 6.2, 5.8, 6.1, 5.9, 6.0])])}
    res = run_test(g, [1, 2, 3], cond_names={1: "A", 2: "B", 3: "C"})
    assert res["design"] == "unpaired"
    assert res["test"] in ("one-way ANOVA", "Kruskal-Wallis")
    assert res["ok"] and res["p"] < 0.05
    assert res["effect_size"]["name"] in ("partial eta^2", "epsilon^2")


def test_kruskal_effect_size_is_epsilon_squared():
    # heavy outliers force a non-normal (Kruskal) path; assert honest epsilon^2 effect size
    g = {"paired": False, "counts": {1: 6, 2: 6, 3: 6},
         "rows": rows([(i, 1, v) for i, v in enumerate([1.0, 1.0, 1.0, 1.0, 1.0, 9.0])]
                      + [(10 + i, 2, v) for i, v in enumerate([2.0, 2.0, 2.0, 2.0, 2.0, 18.0])]
                      + [(20 + i, 3, v) for i, v in enumerate([3.0, 3.0, 3.0, 3.0, 3.0, 27.0])])}
    res = run_test(g, [1, 2, 3], cond_names={1: "A", 2: "B", 3: "C"})
    if res["test"] == "Kruskal-Wallis":
        assert res["effect_size"]["name"] == "epsilon^2"
        assert res["effect_size"]["value"] >= 0.0
        assert "rank-biserial" not in res["interpretation"]
    else:
        # if normality wasn't rejected on this small sample, at least ensure no fake rank-biserial=0
        assert res["effect_size"]["name"] in ("partial eta^2", "epsilon^2")


def test_compare_adds_normalize_tag(tmp_path):
    class DB:
        def __init__(self, rows): self._rows = rows
        def recordings_for_conditions(self, e, cids): return [r for r in self._rows if r["condition_id"] in cids]
        def recordings_for_experiment(self, e): return list(self._rows)
    from hub.analysis.compare import compare
    def mk(name, vals):
        p = tmp_path / name
        p.write_text("t_offset,signal,value\n" + "".join(f"{i*0.1},shimmer.gsr,{v}\n" for i, v in enumerate(vals)))
        return str(p)
    rows = []
    for pid in (1, 2, 3):
        rows.append({"participant_id": pid, "condition_id": 1, "csv_path": mk(f"{pid}a", [1.0 + pid, 2.0 + pid, 3.0 + pid])})
        rows.append({"participant_id": pid, "condition_id": 2, "csv_path": mk(f"{pid}b", [4.0 + pid, 5.0 + pid, 6.0 + pid])})
    res = compare(DB(rows), 1, [1, 2], "shimmer.gsr", "mean", "participant", {1: "A", 2: "B"}, normalize="zscore")
    assert res["normalize"] == "zscore"
    assert res["ok"] is True and res["signal"] == "shimmer.gsr"
