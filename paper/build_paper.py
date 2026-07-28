"""Build the paper PDF from PAPER.md. Run it, do not hand-edit build/.

    python3 build_paper.py

Reads PAPER.md, applies the LaTeX-facing transforms below, and drives
pandoc -> tectonic. Writes build/paper.{md,tex,pdf} and a dated copy at the
repository root.

The transforms exist because PAPER.md is written to be readable on GitHub and
LaTeX needs a different shape for the same content:

  - the human header block becomes YAML frontmatter
  - section marks (§ 5) become "Section 5"; § renders badly in the body font
  - β and → become math so they do not depend on the font having the glyph
  - figures switch from .svg (GitHub renders it) to .pdf (LaTeX embeds it), and
    the italic caption line following each image is folded into the image's
    alt text, which is where pandoc looks for a caption
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
BUILD = ROOT / "build"
DATE = "2026-07-27"

# The header block at the top of PAPER.md, lifted into YAML. Kept here rather
# than parsed out of the markdown so the PDF's metadata is explicit.
TITLE = "The Evaluator Trust Boundary"
SUBTITLE = (
    "A defect class in AI evaluation infrastructure, its prevalence across "
    "36 organizations, and its removal by training"
)
# Personal name, corporate affiliation. The DOI citation is built from this
# field, so a company-only author line would credit the company and not the
# person for a paper going out under a permanent identifier.
# Personal name only. The DOI citation is built from this field, so a
# company-only line would credit the company rather than the person for a
# paper carrying a permanent identifier.
#
# The affiliation is NOT appended here. Pandoc escapes this string on its
# way into \author{}, so a LaTeX line break becomes a literal backslash on
# the title page and leaks into the PDF metadata. It is set by \postauthor
# in preamble.tex instead.
AUTHOR = "John Kearney"


def yaml_escape(text: str) -> str:
    """Indent a paragraph under a YAML block scalar."""
    return "\n".join("  " + line if line else "" for line in text.splitlines())


def transform_body(body: str) -> str:
    # Fold "![alt](fig.svg)\n\n*Figure N. Caption*" into "![Caption](fig.pdf)".
    # Pandoc reads the alt text as the caption, so the separate italic line
    # would otherwise print twice.
    body = re.sub(
        r"!\[[^\]]*\]\((figures/[^)]+)\.svg\)\s*\n\s*\n\*Figure \d+\.\s*([^*]+?)\*",
        lambda m: f"![{m.group(2).strip()}]({m.group(1)}.pdf)",
        body,
    )
    body = body.replace(".svg)", ".pdf)")  # any figure without a caption line

    body = re.sub(r"§\s?(\d)", r"Section \1", body)
    body = body.replace("β", r"$\beta$")
    body = body.replace("→", r"$\rightarrow$")
    return body


def main() -> int:
    for tool in ("pandoc", "tectonic"):
        if not shutil.which(tool):
            print(f"error: {tool} not on PATH", file=sys.stderr)
            return 1

    src = (ROOT / "PAPER.md").read_text()

    # Abstract is the paragraph after the "## Abstract" heading; body starts at
    # section 1. Anything between them is header prose that the YAML replaces.
    abstract = src.split("## Abstract", 1)[1].split("##", 1)[0].strip()
    body = src[src.index("## 1.") :].strip()

    doc = "\n".join(
        [
            "---",
            f'title: "{TITLE}"',
            f'subtitle: "{SUBTITLE}"',
            f'author: "{AUTHOR}"',
            f'date: "{DATE}"',
            "abstract: |",
            yaml_escape(abstract),
            "---",
            "",
            transform_body(body),
            "",
        ]
    )

    BUILD.mkdir(exist_ok=True)
    (BUILD / "paper.md").write_text(doc)
    shutil.copy(ROOT / "references.bib", BUILD / "references.bib")
    figures = BUILD / "figures"
    figures.mkdir(exist_ok=True)
    for fig in (ROOT / "figures").glob("*.pdf"):
        shutil.copy(fig, figures / fig.name)

    # --natbib, not --citeproc: the paper cites with \citep{} in the markdown,
    # which pandoc passes through as raw LaTeX for natbib and bibtex to resolve.
    # --citeproc would leave every \citep unresolved and silently drop the
    # bibliography.
    subprocess.run(
        [
            "pandoc", "paper.md",
            "--from", "markdown",
            "--to", "latex",
            "--standalone",
            "--natbib",
            "--bibliography", "references.bib",
            "--variable", "biblio-style=plainnat",
            "--variable", "documentclass=article",
            "--variable", "fontsize=11pt",
            # Typography lives in preamble.tex, injected on top of pandoc's
            # default template rather than replacing it, so pandoc's longtable
            # and graphics machinery keeps working.
            "--include-in-header", "../preamble.tex",
            "-o", "paper.tex",
        ],
        cwd=BUILD,
        check=True,
    )
    subprocess.run(
        ["tectonic", "paper.tex", "--print", "--keep-logs"],
        cwd=BUILD,
        check=True,
    )

    out = ROOT / f"The-Evaluator-Trust-Boundary-{DATE}.pdf"
    shutil.copy(BUILD / "paper.pdf", out)
    print(f"\nwrote {out.relative_to(ROOT)} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
