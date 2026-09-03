from pathlib import Path

import pytest
import yaml

from hub.kit_study.orders import KIND_SEQUENCE, load_block

F1 = Path("hub/kit_study/configs/orders_f1.yaml")


def test_load_f1_block():
    block = load_block(F1)
    assert block.family == "F1"
    assert tuple(o.kind for o in block.orders) == KIND_SEQUENCE
    rush = block.orders[2]
    assert rush.time_limit_s == 150
    assert 8 <= len(rush.parts) <= 10
    pert = block.orders[5]
    assert pert.perturbation is not None and pert.perturbation.kind == "swap_parts"
    for order in block.orders:
        slots = [p.depot_slot for p in order.parts]
        ids = [p.id for p in order.parts]
        assert len(set(slots)) == len(slots), order.id
        assert len(set(ids)) == len(ids), order.id


def test_bad_kind_sequence_rejected(tmp_path):
    data = yaml.safe_load(F1.read_text())
    data["orders"][0]["kind"] = "rush"
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="kind sequence"):
        load_block(bad)


def test_rush_requires_time_limit(tmp_path):
    data = yaml.safe_load(F1.read_text())
    data["orders"][2]["time_limit_s"] = None
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="time_limit_s"):
        load_block(bad)
