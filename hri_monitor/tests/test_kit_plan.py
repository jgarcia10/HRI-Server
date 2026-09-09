from collections import Counter

from hub.kit_study.plan import GROUPS, assign


def test_four_consecutive_participants_cover_all_four_groups():
    groups = [assign(f"P{n:02d}")["group"] for n in range(1, 5)]
    assert sorted(groups) == [1, 2, 3, 4]
    assert assign("P05")["group"] == assign("P01")["group"]


def test_blocks_alternate_condition_and_family():
    for n in range(1, 9):
        plan = assign(f"P{n:02d}")
        b1, b2 = plan["blocks"]
        assert {b1["condition"], b2["condition"]} == {"C0", "C1"}
        assert {b1["family"], b2["family"]} == {"F1", "F2"}
        assert b1["orders"] == f"orders_{b1['family'].lower()}.yaml"


def test_order_and_family_are_balanced_over_a_cycle():
    plans = [assign(f"P{n:02d}") for n in range(1, 5)]
    first_cond = Counter(p["blocks"][0]["condition"] for p in plans)
    first_fam = Counter(p["blocks"][0]["family"] for p in plans)
    assert first_cond == {"C0": 2, "C1": 2} and first_fam == {"F1": 2, "F2": 2}
    assert len(GROUPS) == 4


def test_non_numeric_code_is_stable():
    assert assign("pilot")["group"] == assign("pilot")["group"]
    assert assign("pilot")["number"] is None
