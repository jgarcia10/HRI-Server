"""Render a combined violin + box + points figure to SVG/PDF bytes (headless)."""
import io

import matplotlib
matplotlib.use("Agg")  # no display; must precede pyplot import
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def figure_bytes(values, condition_order, title, ylabel, fmt) -> bytes:
    """values: [{condition, subject, value}]. Returns SVG or PDF bytes."""
    groups = [[v["value"] for v in values if v["condition"] == c] for c in condition_order]
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    positions = list(range(1, len(condition_order) + 1))
    nonempty = [(p, g) for p, g in zip(positions, groups) if len(g) > 0]
    if nonempty:
        vp_pos = [p for p, g in nonempty]
        vp_data = [g for p, g in nonempty]
        parts = ax.violinplot(vp_data, positions=vp_pos, showextrema=False)
        for body in parts["bodies"]:
            body.set_facecolor("#38bdf8"); body.set_alpha(0.25)
        ax.boxplot(vp_data, positions=vp_pos, widths=0.18, showfliers=False,
                   patch_artist=True,
                   boxprops=dict(facecolor="white", edgecolor="#0284c7"),
                   medianprops=dict(color="#0284c7"))
        rng = np.random.RandomState(0)
        for p, g in nonempty:
            jitter = (rng.rand(len(g)) - 0.5) * 0.12
            ax.scatter(np.full(len(g), p) + jitter, g, s=18, color="#0c4a6e", alpha=0.7, zorder=3)
    ax.set_xticks(positions)
    ax.set_xticklabels(condition_order, rotation=0)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.tight_layout()
    buf = io.BytesIO()
    try:
        fig.savefig(buf, format=fmt)
    finally:
        plt.close(fig)
    return buf.getvalue()
