"""Draw the trust-boundary figure used in Section 2.

The name "Evaluator Trust Boundary" is a spatial claim, so the paper should show
the space. Two sets: what the scorer reads, and what the evaluated system can
write. The violation is the intersection, and the invariant is that it should be
empty.

    python3 make_boundary_figure.py     ->  figures/trust_boundary.{pdf,svg,png}
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

OUT = Path(__file__).parent / "figures"

INK = "#1a1a1a"
TRUSTED = "#2f6f4f"
CONTROLLED = "#8c2f39"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.0, 3.6))

    left, right, r = (-0.75, 0.0), (0.75, 0.0), 1.45

    ax.add_patch(Circle(left, r, facecolor=TRUSTED, alpha=0.20,
                        edgecolor=TRUSTED, linewidth=1.4, zorder=2))
    ax.add_patch(Circle(right, r, facecolor=CONTROLLED, alpha=0.20,
                        edgecolor=CONTROLLED, linewidth=1.4, zorder=2))

    ax.text(-1.55, 1.02, "State the scorer reads", ha="center", va="center",
            fontsize=11, color=TRUSTED, fontweight="bold")
    ax.text(1.55, 1.02, "State the evaluated\nsystem can write", ha="center",
            va="center", fontsize=11, color=CONTROLLED, fontweight="bold")

    ax.text(-1.55, 0.36, "rubric, frozen\nground truth,\nthe judge's own\nstructured output",
            ha="center", va="center", fontsize=8.5, color=INK, linespacing=1.45)
    ax.text(1.55, 0.36, "the answer, its\nreasoning, tool\narguments, stdout,\nthe transcript",
            ha="center", va="center", fontsize=8.5, color=INK, linespacing=1.45)

    # The intersection is the whole point, so it is the only labelled region.
    ax.text(0, 0.30, "ETB", ha="center", va="center", fontsize=15,
            fontweight="bold", color=INK, zorder=4)
    ax.text(0, -0.16, "the score depends\non something the\nevaluated system\ncan influence",
            ha="center", va="center", fontsize=8, color=INK, linespacing=1.4, zorder=4)

    ax.annotate(
        "the invariant: this region must be empty",
        xy=(0, -0.95), xytext=(0, -1.92), ha="center", va="center",
        fontsize=9.5, style="italic", color=INK,
        arrowprops=dict(arrowstyle="->", color=INK, linewidth=0.9,
                        shrinkA=0, shrinkB=2),
    )

    ax.set_xlim(-3.4, 3.4)
    ax.set_ylim(-2.3, 1.75)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout(pad=0.2)

    for ext in ("pdf", "svg", "png"):
        fig.savefig(OUT / f"trust_boundary.{ext}", bbox_inches="tight",
                    dpi=200 if ext == "png" else None)
    print(f"wrote {OUT}/trust_boundary.{{pdf,svg,png}}")


if __name__ == "__main__":
    main()
