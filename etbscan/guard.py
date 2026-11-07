"""Drop-in hardening helpers for graders and judge prompts: the fixes etb-scan keeps recommending.

Standard library only, no model calls. Each helper closes one ETB pattern the lint flags:

- :func:`last_verdict`  ETB-01  read the judge's final verdict, not the first token that looks like one
- :func:`exact_token`   ETB-01  accept a bare-letter or single-word verdict only when it is the whole reply
- :func:`last_label`    ETB-01  choose the label that occurs last, not the first in a fixed check order
- :func:`neutralize_markers`, :func:`fence`  ETB-02  make candidate text unable to impersonate the template
- :func:`render_prompt` ETB-02  single-pass substitution with candidate fields fenced and neutralised
- :func:`hardened_restore_lines` ETB-11  a test-file restore that fails closed in an eval shell script

    from etbscan.guard import last_verdict, render_prompt
    verdict = last_verdict(judgment, r"^correct: (yes|no)\\s*$", allowed=("yes", "no"))  # None if absent
    prompt = render_prompt(TEMPLATE, {"question": q, "response": r}, candidate_fields=("response",))
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable, Mapping, Sequence

MIDDLE_DOT = "·"
_PLACEHOLDER = re.compile(r"\{(\w+)\}|<<(\w+)>>")
_MARKER_SHAPES = (
    re.compile(r"^\s*(\[[^\]\n]{1,60}\]:?)", re.MULTILINE),  # [Submission]: / [BEGIN DATA] / [The Start of ...]
    re.compile(r"(<\|[^|\n]{1,60}\|>)"),  # <|The Start of Assistant A's Answer|>
    re.compile(r"^\s*(#{1,4} [^\n]{1,60})$", re.MULTILINE),  # markdown headers
    re.compile(r"^\s*([A-Za-z_][\w ]{0,40}:)(?=\s|$)", re.MULTILINE),  # label: ... (field labels, verdict lines)
    re.compile(r"(```\w*)"),  # fences
    re.compile(r"(\"\"\")"),  # triple quotes
)


def last_verdict(text: str, pattern: str, allowed: Iterable[str] | None = None,
                 flags: int = re.MULTILINE) -> str | None:
    """The last match of `pattern` in `text` (group 1 if the pattern has one), validated.

    Returns None when nothing matches or the match is not in `allowed`; never a default pass.
    """
    hits = re.findall(pattern, text, flags)
    if not hits:
        return None
    hit = hits[-1]
    if isinstance(hit, tuple):
        hit = next((h for h in hit if h), "")
    value = hit.strip()
    if allowed is not None:
        table = {a.strip().lower(): a for a in allowed}
        return table.get(value.lower())
    return value or None


def exact_token(text: str, allowed: Iterable[str]) -> str | None:
    """Accept the reply only if, stripped of whitespace and punctuation, it is exactly one allowed token."""
    cleaned = re.sub(r"^[\s\W_]+|[\s\W_]+$", "", text)
    table = {a.strip().lower(): a for a in allowed}
    return table.get(cleaned.lower())


def last_label(text: str, labels: Iterable[str]) -> str | None:
    """Of the given labels, the one whose last occurrence is latest in `text`; None if none occurs."""
    best, best_pos = None, -1
    for label in labels:
        pos = text.rfind(label)
        if pos > best_pos:
            best, best_pos = label, pos
    return best


def detect_markers(template: str) -> list[str]:
    """Structural tokens of a prompt template (field labels, delimiters, headers, fences)."""
    found: list[str] = []
    for rx in _MARKER_SHAPES:
        for m in rx.findall(template):
            tok = m if isinstance(m, str) else m[0]
            tok = tok.strip()
            if tok and tok not in found and not _PLACEHOLDER.fullmatch(tok):
                found.append(tok)
    return found


def neutralize_markers(text: str, markers: Iterable[str]) -> str:
    """Break every structural marker inside candidate text so it cannot read as the template's own.

    Deterministic and idempotent: a space becomes a dash, otherwise a middle dot is inserted after
    the first character. Literal space (not \\s) matters: a no-break space would let a model
    pre-neutralise its own text and bypass the check.
    """
    out = text
    for m in sorted(set(markers), key=len, reverse=True):
        if not m:
            continue
        safe = m.replace(" ", "-") if " " in m else m[:1] + MIDDLE_DOT + m[1:]
        out = re.sub(re.escape(m), safe, out, flags=re.IGNORECASE)
    return out


def fence(text: str, tag: str = "candidate") -> str:
    """Wrap candidate text in an explicit delimiter the text itself cannot forge."""
    open_, close = f"<<{tag}>>", f"<</{tag}>>"
    body = neutralize_markers(text, (open_, close))
    return f"{open_}\n{body}\n{close}"


def render_prompt(template: str, fields: Mapping[str, str], candidate_fields: Sequence[str],
                  markers: Iterable[str] | None = None, fence_tag: str | None = "candidate") -> str:
    """Substitute `{name}` / `<<name>>` placeholders in one pass.

    Candidate fields are neutralised against the template's markers (detected when not given) and
    fenced; other fields are inserted as is. A placeholder literal inside an inserted value is never
    expanded, which is what chained `str.replace` calls get wrong.
    """
    marks = list(markers) if markers is not None else detect_markers(template)

    def value_for(name: str) -> str:
        v = str(fields.get(name, ""))
        if name in candidate_fields:
            v = neutralize_markers(v, marks)
            if fence_tag:
                v = fence(v, fence_tag)
        return v

    return _PLACEHOLDER.sub(lambda m: value_for(m.group(1) or m.group(2)), template)


def hardened_restore_lines(ref: str, paths: Sequence[str], created: Sequence[str],
                           fail_marker: str = ">>>>> Reset Failed") -> list[str]:
    """Shell lines that restore test files before grading and fail closed.

    Paths the test patch creates are deleted; the rest are checked out from `ref` with `--`; any
    failure echoes `fail_marker` and exits, so a grader that treats the marker as failed never runs
    tests on an agent-edited tree.
    """
    created_set = set(created)
    keep = [p for p in paths if p not in created_set]
    drop = [p for p in paths if p in created_set]
    lines: list[str] = []
    if drop:
        lines.append("rm -f " + " ".join(shlex.quote(p) for p in drop))
    if keep:
        lines.append(f"git checkout {shlex.quote(ref)} -- " + " ".join(shlex.quote(p) for p in keep)
                     + f" || {{ echo {shlex.quote(fail_marker)}; exit 1; }}")
    return lines


__all__ = [
    "detect_markers",
    "exact_token",
    "fence",
    "hardened_restore_lines",
    "last_label",
    "last_verdict",
    "neutralize_markers",
    "render_prompt",
]
