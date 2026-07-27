"""Draw the trust-boundary figure used in Section 2.

The name "Evaluator Trust Boundary" is a spatial claim, so the paper shows the
space once: two sets, and the violation as their intersection.

The left set is deliberately "determines the verdict" and not "read by the
scorer". A judge has to read the answer it is grading, and most of what the
evaluated system writes is exactly what the evaluator is supposed to look at.
Drawing the sets as read-versus-written would put that necessary case inside
the violation. The invariant is about what the score is a function of.

Set plainly, to sit inside a serif single-column paper without announcing
itself: serif type below body size, hairline outlines, one grey for the lens,
and only the three labels it needs. Everything else belongs in the caption.

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
})

INK = "#1a1a1a"
LENS = "#c3c8cd"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    # Wide and short: a diagram should cost the page about what a paragraph does.
    fig, ax = plt.subplots(figsize=(5.2, 1.6))

    r, dx = 1.02, 0.50
    left, right = (-dx, 0.0), (dx, 0.0)

    # The lens is the right circle clipped to the left one. Building it from two
    # arcs by hand gets the point ordering wrong and fills a bowtie instead.
    clip = Circle(left, r, transform=ax.transData)
    lens = Circle(right, r, facecolor=LENS, edgecolor="none", zorder=2)
    ax.add_patch(lens)
    lens.set_clip_path(clip)

    for centre in (left, right):
        ax.add_patch(Circle(centre, r, facecolor="none", edgecolor=INK,
                            linewidth=1.0, zorder=3))

    # NOT "read by the scorer". The scorer must read the candidate's answer;
    # that is the measurement, not the defect. The invariant is about what the
    # verdict is a FUNCTION OF, so that is what the left set has to be.
    ax.text(-1.06, 0.0, "determines\nthe verdict", ha="center", va="center",
            fontsize=7.5, color=INK, linespacing=1.35, zorder=4)
    # Three lines, not two: on two, this reaches the circle's edge and the
    # descender touches the stroke.
    ax.text(1.06, 0.0, "controlled by\nthe evaluated\nsystem", ha="center",
            va="center", fontsize=7.5, color=INK, linespacing=1.35, zorder=4)
    ax.text(0.0, 0.0, "ETB", ha="center", va="center", fontsize=9,
            color=INK, zorder=4)

    ax.set_xlim(-1.82, 1.82)
    ax.set_ylim(-1.08, 1.08)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout(pad=0.02)

    for ext in ("pdf", "svg", "png"):
        fig.savefig(OUT / f"trust_boundary.{ext}", bbox_inches="tight",
                    dpi=300 if ext == "png" else None)
    print(f"wrote {OUT}/trust_boundary.{{pdf,svg,png}}")


if __name__ == "__main__":
    main()
