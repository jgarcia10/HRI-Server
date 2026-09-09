"""Order/block specifications for the kit-assembly study. Pure data + YAML loader."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

KIND_SEQUENCE = ("easy", "easy", "rush", "easy", "rush_prime", "perturbed")
_TIMED_KINDS = {"rush", "rush_prime", "perturbed"}
_PART_RANGE = {"easy": (4, 5), "rush": (8, 10), "rush_prime": (8, 10), "perturbed": (5, 7)}


@dataclass(frozen=True)
class PartSpec:
    id: str
    type: str
    color: str
    depot_slot: str


@dataclass(frozen=True)
class Perturbation:
    window: tuple[float, float]
    kind: str


@dataclass(frozen=True)
class OrderSpec:
    id: str
    kind: str
    parts: list[PartSpec]
    time_limit_s: float | None
    perturbation: Perturbation | None


@dataclass(frozen=True)
class BlockSpec:
    family: str
    orders: list[OrderSpec]


def load_block(path: str | Path) -> BlockSpec:
    raw = yaml.safe_load(Path(path).read_text())
    # Check kind sequence first (before parsing, to catch sequence errors early)
    kinds = tuple(o["kind"] for o in raw.get("orders", []))
    if kinds != KIND_SEQUENCE:
        raise ValueError(f"kind sequence must be {KIND_SEQUENCE}, got {kinds}")
    orders = [_parse_order(o) for o in raw.get("orders", [])]
    return BlockSpec(family=str(raw["family"]), orders=orders)


def _parse_order(o: dict) -> OrderSpec:
    kind = o["kind"]
    parts = [PartSpec(str(p["id"]), str(p["type"]), str(p["color"]), str(p["depot_slot"]))
             for p in o["parts"]]
    lo, hi = _PART_RANGE.get(kind, (1, 99))
    if not lo <= len(parts) <= hi:
        raise ValueError(f"{o['id']}: {kind} order needs {lo}-{hi} parts, got {len(parts)}")
    for field in ("id", "depot_slot"):
        vals = [getattr(p, "id" if field == "id" else "depot_slot") for p in parts]
        if len(set(vals)) != len(vals):
            raise ValueError(f"{o['id']}: duplicate part {field}")
    limit = o.get("time_limit_s")
    if kind in _TIMED_KINDS and not limit:
        raise ValueError(f"{o['id']}: {kind} order requires time_limit_s")
    pert = None
    if kind == "perturbed":
        p = o.get("perturbation")
        if not p:
            raise ValueError(f"{o['id']}: perturbed order requires perturbation")
        pert = Perturbation(window=(float(p["window"][0]), float(p["window"][1])),
                            kind=str(p["kind"]))
    return OrderSpec(id=str(o["id"]), kind=kind, parts=parts,
                     time_limit_s=float(limit) if limit else None, perturbation=pert)
