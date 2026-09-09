"""Order/block specifications for the kit-assembly study. Pure data + YAML loader."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

KIND_SEQUENCE = ("easy", "easy", "rush", "easy", "rush_prime", "perturbed")
_TIMED_KINDS = {"rush", "rush_prime", "perturbed"}
_PART_RANGE = {"easy": (4, 5), "rush": (8, 10), "rush_prime": (8, 10), "perturbed": (5, 7)}


PART_WIDTH = {"1x2": 2, "1x1": 1, "slope": 1}   # front-view width in studs


@dataclass(frozen=True)
class PartSpec:
    id: str
    type: str
    color: str
    depot_slot: str
    pos: tuple[int, int] = (0, 0)      # (x in studs from the left, layer from the table)
    high: str | None = None            # slopes only: which side is the tall edge ("left"/"right")

    def as_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "color": self.color, "depot_slot": self.depot_slot,
                "pos": list(self.pos), "high": self.high, "width": PART_WIDTH.get(self.type, 1)}


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
    name: str = ""                      # figure name shown to the participant ("Tower")
    width_studs: int = 0                # footprint width of the finished figure


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
    parts = []
    for p in o["parts"]:
        pos = tuple(int(v) for v in p.get("pos", (0, 0)))
        high = p.get("high")
        if p["type"] == "slope" and high not in ("left", "right"):
            raise ValueError(f"{o['id']}/{p['id']}: slope needs high: left|right")
        parts.append(PartSpec(str(p["id"]), str(p["type"]), str(p["color"]), str(p["depot_slot"]),
                              pos=pos, high=high if p["type"] == "slope" else None))
    cells: set[tuple[int, int]] = set()
    for p in parts:
        for dx in range(PART_WIDTH.get(p.type, 1)):
            cell = (p.pos[0] + dx, p.pos[1])
            if cell in cells:
                raise ValueError(f"{o['id']}: {p.id} overlaps another part at {cell}")
            cells.add(cell)
    width = int(o.get("width_studs") or (max(c[0] for c in cells) + 1))
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
                     time_limit_s=float(limit) if limit else None, perturbation=pert,
                     name=str(o.get("name", "")), width_studs=width)
