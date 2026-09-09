"""Counterbalancing plan per participant (design doc §Design): condition order (C0→C1 /
C1→C0) × structure family of block 1 (F1 / F2) = four groups, assigned round-robin from the
participant number, so every 4 consecutive participants cover all four cells.

Block 2 always uses the *other* family, so no kit is ever assembled twice by one person
(F2 is the mirrored/recoloured twin of F1, see the brick set document)."""
from __future__ import annotations

import re

FAMILY_FILE = {"F1": "orders_f1.yaml", "F2": "orders_f2.yaml"}

# group -> (condition of block 1, condition of block 2, family of block 1)
GROUPS = (
    ("C0", "C1", "F1"),
    ("C1", "C0", "F2"),
    ("C0", "C1", "F2"),
    ("C1", "C0", "F1"),
)


def participant_number(code: str) -> int | None:
    """P07 → 7, p12b → 12, 'pilot' → None (falls back to a stable hash)."""
    m = re.search(r"(\d+)", code or "")
    return int(m.group(1)) if m else None


def assign(code: str) -> dict:
    n = participant_number(code)
    group = (n - 1) % 4 if n is not None and n > 0 else sum(map(ord, code or "")) % 4
    c1, c2, fam1 = GROUPS[group]
    fam2 = "F2" if fam1 == "F1" else "F1"
    blocks = [
        {"block": 1, "condition": c1, "family": fam1, "orders": FAMILY_FILE[fam1]},
        {"block": 2, "condition": c2, "family": fam2, "orders": FAMILY_FILE[fam2]},
    ]
    return {"participant": code, "number": n, "group": group + 1, "blocks": blocks,
            "label": f"{c1}/{fam1} → {c2}/{fam2}"}
