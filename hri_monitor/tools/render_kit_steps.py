#!/usr/bin/env python3
"""Render every assembly step of every kit as a diagram PNG, and optionally ask Gemini for a
photo-realistic version of each step (diagram passed as the reference image, so the geometry
is preserved).

    .venv/bin/python tools/render_kit_steps.py                 # diagrams only → data/kit_steps/
    GEMINI_API_KEY=... .venv/bin/python tools/render_kit_steps.py --photoreal [--only F1-O1]

The photo-real pass needs `pip install google-genai` and a Gemini API key (https://aistudio.google.com/apikey).
Model: gemini-2.5-flash-image (Nano Banana). ~74 steps + 12 finished figures ≈ 86 images.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hub.kit_study.orders import PART_WIDTH, load_block  # noqa: E402

COLOR = {"red": "#d64541", "orange": "#e67e22", "blue": "#2e86de", "seafoam": "#7fd6c2", "lime": "#a3cb38"}
NAME = {"1x2": "long brick (1x2, two studs)", "1x1": "small cube brick (1x1)", "slope": "sloped roof brick"}


def draw(ax, parts, step, width, ghost=True):
    """Front view: placed parts solid, current part highlighted, future parts as faint outlines."""
    ax.set_aspect("equal"); ax.axis("off")
    ax.plot([-0.3, width + 0.3], [0, 0], color="#666", lw=2)
    for i, p in enumerate(parts):
        x, layer = p.pos; w = PART_WIDTH[p.type]
        if p.type == "slope":
            pts = [(x, layer), (x + w, layer), (x + w, layer + 1)] if p.high == "right" else \
                  [(x, layer), (x + w, layer), (x, layer + 1)]
            patch = Polygon(pts, closed=True)
        else:
            patch = Rectangle((x, layer), w, 1)
            for s in range(w):  # studs
                ax.add_patch(Rectangle((x + s + 0.3, layer + 1), 0.4, 0.15, fc=COLOR[p.color], ec="#333", lw=0.8,
                                       alpha=1 if i <= step else 0.15))
        if i < step:
            patch.set(fc=COLOR[p.color], ec="#222", lw=1.2)
        elif i == step:
            patch.set(fc=COLOR[p.color], ec="white", lw=4, zorder=5)
        else:
            patch.set(fc="none", ec="#999", lw=1, ls="--", alpha=0.6 if ghost else 0)
        ax.add_patch(patch)
    ax.set_xlim(-0.6, width + 0.6)
    ax.set_ylim(-0.4, max(p.pos[1] for p in parts) + 1.8)


def placement_prompt(parts, step, width):
    p = parts[step]
    placed = ", ".join(f"{q.color} {NAME[q.type]} at x={q.pos[0]} layer={q.pos[1]}" for q in parts[:step]) or "nothing yet"
    return (f"Photorealistic photo, front view slightly from above, of big glossy toddler building bricks "
            f"(Mega Bloks style, large round studs) on a white foam mat on a light grey table, soft daylight. "
            f"Reproduce EXACTLY the layout of the reference diagram: 1 stud = 1 unit, figure width {width} studs. "
            f"Already placed: {placed}. The piece being added now is the {p.color} {NAME[p.type]} at x={p.pos[0]} "
            f"layer={p.pos[1]}" + (f", tall edge on the {p.high}" if p.high else "") +
            "; show it slightly lifted above its final position with a subtle glow. Dashed outlines in the "
            "diagram are future pieces: do NOT draw them. No text, no hands, no logos.")


def photoreal(client, png: Path, prompt: str, out: Path):
    from PIL import Image
    resp = client.models.generate_content(model="gemini-2.5-flash-image",
                                          contents=[prompt, Image.open(png)])
    for part in resp.candidates[0].content.parts:
        if getattr(part, "inline_data", None) is not None:
            out.write_bytes(part.inline_data.data); return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "kit_steps"))
    ap.add_argument("--photoreal", action="store_true", help="also ask Gemini for photo-real renders")
    ap.add_argument("--only", default=None, help="e.g. F1-O1 to limit to one kit")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    client = None
    if args.photoreal:
        if not os.environ.get("GEMINI_API_KEY"):
            print("GEMINI_API_KEY not set — diagrams only", file=sys.stderr)
        else:
            from google import genai
            client = genai.Client()
    n = 0
    for fam in ("f1", "f2"):
        block = load_block(ROOT / "hub" / "kit_study" / "configs" / f"orders_{fam}.yaml")
        for order in block.orders:
            tag = f"{block.family}-{order.id}"
            if args.only and args.only != tag:
                continue
            parts, width = order.parts, order.width_studs
            for step in range(len(parts) + 1):        # last index = finished figure
                fig, ax = plt.subplots(figsize=(4, 4))
                draw(ax, parts, step, width, ghost=step < len(parts))
                title = f"{order.name} — piece {step + 1} of {len(parts)}" if step < len(parts) else f"{order.name} — finished"
                ax.set_title(title, fontsize=11)
                png = out / f"{tag}_step{step:02d}.png"
                fig.savefig(png, dpi=110, bbox_inches="tight"); plt.close(fig); n += 1
                if client is not None:
                    prompt = placement_prompt(parts, step, width) if step < len(parts) else \
                        placement_prompt(parts, len(parts) - 1, width).replace("being added now", "on top, already placed")
                    ok = photoreal(client, png, prompt, out / f"{tag}_step{step:02d}_photo.png")
                    print(tag, step, "photo" if ok else "NO IMAGE")
    print(f"{n} diagrams in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
