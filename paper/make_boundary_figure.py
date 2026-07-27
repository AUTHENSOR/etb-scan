"""Draw the trust-boundary figure used in Section 2.

The name "Evaluator Trust Boundary" is a spatial claim, so the paper shows the
space once: two sets, and the violation as their intersection.

Deliberately small and plain. It sits inside a serif, single-column paper, so it
is set in a serif face at body-text size, in one muted colour, and carries only
the three labels it needs. Detail belongs in the caption and in Table 1, not
crammed inside the circles.

    python3 make_boundary_figure.py     ->  figures/trust_boundary.{pdf,svg,png}
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

OUT = Path(__file__).parent / "figures"

matplotlib.rcParams.update({
    "font.family": "serif",
    # Closest match available to the document's Latin Modern.
    "font.serif": ["STIXGeneral", "DejaVu Serif"],
    "mathtext.fontset": "stix",
})

INK = "#111111"
EDGE = "#555555"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    # Wide and short: it is a diagram, not an illustration, and it should cost
    # the page as little vertical space as a paragraph would.
    fig, ax = plt.subplots(figsize=(5.0, 1.75))

    r = 1.0
    left, right = (-0.52, 0.0), (0.52, 0.0)

    for centre in (left, right):
        ax.add_patch(Circle(centre, r, facecolor=INK, alpha=0.07,
                            edgecolor=EDGE, linewidth=0.8, zorder=2))

    ax.text(-1.18, 0.0, "read by\nthe scorer", ha="center", va="center",
            fontsize=8.5, color=INK, linespacing=1.4)
    ax.text(1.18, 0.0, "written by the\nevaluated system", ha="center",
            va="center", fontsize=8.5, color=INK, linespacing=1.4)
    ax.text(0.0, 0.0, "ETB", ha="center", va="center", fontsize=10.5,
            color=INK, zorder=4)

    ax.set_xlim(-2.25, 2.25)
    ax.set_ylim(-1.12, 1.12)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout(pad=0.05)

    for ext in ("pdf", "svg", "png"):
        fig.savefig(OUT / f"trust_boundary.{ext}", bbox_inches="tight",
                    dpi=200 if ext == "png" else None)
    print(f"wrote {OUT}/trust_boundary.{{pdf,svg,png}}")


if __name__ == "__main__":
    main()
