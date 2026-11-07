"""`etbscan judge-check`: run the judge-side checks against your own grading template.

The spec is a small JSON (or YAML, when PyYAML is installed) file: the prompt template, which
placeholder receives the candidate's text, sample values for the other placeholders, how the
verdict is parsed and which parsed values count as a pass, plus one completion fragment the
parser reads as a pass and the judge's genuine negative verdict. From that, three static checks
run over the template and its parser. No model is called.

* ETB-01 ``judge_echo_parse``: a completion that quotes the candidate (carrying the pass token)
  before the judge's real negative verdict; open if parsed as a pass.
* ETB-03 ``judge_fail_mode``: an empty completion and a verdict-free refusal; open if either passes.
* ETB-02 ``judge_boundary_unescaped``: a candidate that repeats the template's structural markers;
  open if any reaches the rendered prompt unchanged.

Each check runs with the parser as specified (``before``) and again with the hardened reading
(``after``: last well-formed verdict, exact token, markers neutralised inside a fenced
candidate), so the report shows what the fix buys. The fixes are the :mod:`etbscan.guard`
helpers.

Spec fields::

    id: my_grader
    template: |                      # or template_file: path (relative to the spec)
      ... {question} ... {answer} ...  # placeholders in {braces}; <<name>> also accepted
    response_field: answer           # placeholder that receives the candidate
    fields: {question: "What is 6 times 7?"}   # sample values for the other placeholders
    markers: ["[BEGIN DATA]", "GRADE:"]        # optional; derived from the template when absent
    parser:
      kind: first_regex | last_regex | first_letter | exact_token | json_field
      pattern: "GRADE: ([CI])"       # regex kinds: group 1 is the verdict
      ignore_case: false             # regex kinds
      letters: "ABC"                 # first_letter
      field: correct                 # json_field
      pass_values: ["C"]
      other_values: ["I"]            # exact_token: the non-pass tokens the parser accepts
      default: null                  # parsed value when nothing matches (null = unscored)
    pass_text: "GRADE: C"            # fragment the parser reads as a pass
    fail_text: "GRADE: I"            # the judge's genuine negative verdict
    echo_prefix: "The response says: "         # optional
    structured_output: false         # verdict is a typed field, not free text (noted, not assumed)
    single_token: false              # the judge emits one token: nothing can precede the verdict
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}|<<([A-Za-z_][A-Za-z0-9_]*)>>")
MARKER_LINE_RE = re.compile(
    r"^\s*(\[[A-Za-z ]{2,30}\]:?|[A-Z][A-Za-z]*(?: [A-Za-z]+){0,2}:|\*{4,}|={4,}|-{4,}|#{2,}[^\n]{0,40}|<[a-z_]{2,30}>)",
    re.MULTILINE,
)
CANARY = "ETB-CANARY"
REQUIRED_SPEC_KEYS = ("id", "template", "response_field", "parser", "pass_text", "fail_text")

FIXES = {
    "ETB-01": "read only the last well-formed verdict, or require the exact verdict token "
              "(etbscan.guard.last_verdict / exact_token); quoted candidate text can no longer set it",
    "ETB-03": "a missing or malformed verdict must be recorded as unscored, never as a pass",
    "ETB-02": "fence the candidate and neutralise the template's own markers inside it "
              "(etbscan.guard.render_prompt / neutralize_markers)",
}


# -- template -----------------------------------------------------------------------------
def neutralize(text: str, markers: list[str]) -> str:
    """Make every structural marker of the template unmistakable when it appears in candidate text."""
    out = text
    for m in sorted(markers, key=len, reverse=True):
        safe = m.replace(" ", "-") if " " in m else m.replace(":", " :").replace("[", "[ ").replace("#", "# ")
        if safe == m:
            safe = m[:1] + "·" + m[1:]  # middle dot after the first character
        out = re.sub(re.escape(m), safe, out, flags=re.IGNORECASE)
    return out


@dataclass(frozen=True)
class JudgeTemplate:
    """One grading template plus the exact verdict parser applied to the judge's completion."""

    id: str
    used_by: str
    source: str
    template: str
    response_field: str  # the placeholder that receives the candidate's text
    sample_fields: dict[str, str]
    markers: list[str]  # structural tokens of the template (labels, delimiters)
    parse: Callable[[str], Any]
    passes: Callable[[Any], bool]
    pass_fragment: str  # text inside the candidate that a naive parser reads as a pass
    echo_prefix: str  # how a judge that quotes the candidate would introduce it
    negative_verdict: str  # the judge's genuine fail verdict in the required format
    parse_hardened: Callable[[str], Any]
    sanitizes: Callable[[str], str] | None = None  # upstream's own candidate sanitisation, if any
    structured_output: bool = False
    single_token: bool = False  # the judge emits one token: a quote-then-verdict completion cannot exist
    echo_by_design: bool = False
    fail_mode_note: str = ""
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def render(self, response: str, hardened: bool = False) -> str:
        text = response
        if self.sanitizes:
            text = self.sanitizes(text)
        if hardened:
            text = "<<candidate>>\n" + neutralize(text, self.markers) + "\n<</candidate>>"
        fields = dict(self.sample_fields)
        fields[self.response_field] = text
        if f"<<{self.response_field}>>" in self.template:  # spliced with str.replace, in field order
            out = self.template
            for k, v in fields.items():
                out = out.replace(f"<<{k}>>", v)
            return out
        if self.extra.get("render") == "replace_braces":  # literal braces elsewhere in the template
            out = self.template
            for k, v in fields.items():
                out = out.replace("{" + k + "}", v)
            return out
        return self.template.format(**fields)


# -- spec ---------------------------------------------------------------------------------
@dataclass
class JudgeSpec:
    id: str
    template: str
    response_field: str
    parser: dict[str, Any]
    pass_text: str
    fail_text: str
    fields: dict[str, str] = field(default_factory=dict)
    markers: list[str] = field(default_factory=list)
    echo_prefix: str = "The response says: "
    structured_output: bool = False
    single_token: bool = False


def _parse_spec_text(path: Path, text: str) -> dict[str, Any]:
    """JSON with the standard library; anything else through PyYAML when it is importable."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as json_err:
        try:
            import yaml  # optional: `pip install pyyaml`
        except ImportError:
            raise ValueError(
                f"{path}: not valid JSON ({json_err}) and PyYAML is not installed; "
                "write the spec as JSON or `pip install pyyaml` to read YAML"
            ) from None
        raw = yaml.safe_load(text)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: spec must be a mapping, got {type(raw).__name__}")  # noqa: TRY004 - every spec problem is a ValueError
    return raw


def load_spec(path: str | Path) -> JudgeSpec:
    path = Path(path)
    raw = _parse_spec_text(path, path.read_text(encoding="utf-8"))
    if "template_file" in raw and "template" not in raw:
        raw["template"] = (path.parent / raw.pop("template_file")).read_text(encoding="utf-8")
    missing = [k for k in REQUIRED_SPEC_KEYS if k not in raw]
    if missing:
        raise ValueError(f"{path}: spec is missing {missing}")
    known = set(JudgeSpec.__dataclass_fields__)
    return JudgeSpec(**{k: v for k, v in raw.items() if k in known})


def placeholders(template: str) -> list[str]:
    return sorted({a or b for a, b in PLACEHOLDER_RE.findall(template)})


def derive_markers(template: str, response_field: str) -> list[str]:
    """Structural tokens at line starts: bracketed labels, short ``Label:`` prefixes, rules, fences, tags.

    A line longer than 60 characters is prose, not a marker, unless it is a bracketed label or a rule.
    """
    seen: list[str] = []
    for line in template.splitlines():
        m = MARKER_LINE_RE.match(line)
        if not m:
            continue
        tok = m.group(1).strip()
        if tok.endswith(":") and not tok.startswith("[") and len(line.strip()) > 60:
            continue
        if tok and tok not in seen and response_field not in tok:
            seen.append(tok)
    return seen


def _as_value(v: Any) -> Any:
    return None if v is None else str(v)


def build_parsers(parser: dict[str, Any]) -> tuple[Callable[[str], Any], Callable[[str], Any], str]:
    """(as specified, hardened reading, description)."""
    kind = parser.get("kind", "first_regex")
    default = parser.get("default")
    flags = re.IGNORECASE if parser.get("ignore_case") else 0
    if kind in ("first_regex", "last_regex"):
        pat = re.compile(parser["pattern"], flags)

        def first(c: str) -> Any:
            m = pat.search(c)
            return m.group(1) if m and m.groups() else (m.group(0) if m else default)

        def last(c: str) -> Any:
            hits = pat.findall(c)
            if not hits:
                return default
            h = hits[-1]
            return h[0] if isinstance(h, tuple) else h

        return (first if kind == "first_regex" else last), last, f"{kind} {parser['pattern']!r}"
    if kind == "first_letter":
        letters = parser.get("letters", "ABC")
        pat = re.compile(rf"([{re.escape(letters)}])")

        def first_letter(c: str) -> Any:
            m = pat.search(c)
            return m.group(1) if m else default

        def exact(c: str) -> Any:
            s = c.strip()
            return s if s in letters and len(s) == 1 else default

        return first_letter, exact, f"first letter in {letters!r}"
    if kind == "exact_token":
        tokens = [str(t) for t in parser.get("pass_values", [])] + [str(t) for t in parser.get("other_values", [])]

        def exact_tok(c: str) -> Any:
            s = c.strip()
            return s if s in tokens else default

        return exact_tok, exact_tok, f"exact token in {tokens}"
    if kind == "json_field":
        key = parser["field"]

        def json_field(c: str) -> Any:
            try:
                obj = json.loads(c)
            except (json.JSONDecodeError, TypeError):
                return default
            return _as_value(obj.get(key, default)) if isinstance(obj, dict) else default

        def json_last(c: str) -> Any:
            # take the last JSON object in the completion; a quoted object earlier cannot win
            objs = re.findall(r"\{[^{}]*\}", c)
            for cand in reversed(objs):
                try:
                    obj = json.loads(cand)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and key in obj:
                    return _as_value(obj[key])
            return default

        return json_field, json_last, f"json field {key!r}"
    raise ValueError(f"unknown parser kind {kind!r}")


def to_template(spec: JudgeSpec) -> JudgeTemplate:
    parse, parse_hardened, desc = build_parsers(spec.parser)
    pass_values = {str(v) for v in spec.parser.get("pass_values", [])}
    fields = dict(spec.fields)
    for name in placeholders(spec.template):
        if name != spec.response_field and name not in fields:
            fields[name] = f"sample {name}"
    markers = list(spec.markers) or derive_markers(spec.template, spec.response_field)
    return JudgeTemplate(
        id=spec.id, used_by="your grader", source=f"spec {spec.id}", template=spec.template,
        response_field=spec.response_field, sample_fields=fields, markers=markers,
        parse=parse, passes=lambda v: v is not None and str(v) in pass_values,
        pass_fragment=spec.pass_text, echo_prefix=spec.echo_prefix, negative_verdict=spec.fail_text,
        parse_hardened=parse_hardened, sanitizes=None, structured_output=spec.structured_output,
        single_token=spec.single_token, fail_mode_note=f"parser: {desc}; default {spec.parser.get('default')!r}",
        notes="bring-your-own template", extra={},
    )


# -- the three checks, as plain functions over a template ---------------------------------
def _grade(t: JudgeTemplate, completion: str, hardened: bool) -> tuple[bool, Any, str]:
    """(passed, verdict, parser note) for one synthetic completion."""
    parse = t.parse_hardened if hardened else t.parse
    verdict = parse(completion)
    return t.passes(verdict), verdict, f"parser: {'hardened' if parse is not t.parse else 'upstream'}"


def check_echo_parse(t: JudgeTemplate, hardened: bool = False) -> dict[str, Any]:
    """ETB-01: does the parser accept a verdict the judge merely quoted from the candidate?

    The completion quotes the candidate's text (carrying the pass token in the parser's own format)
    the way a judge that explains before it grades would, then ends with the judge's genuine
    negative verdict. A parser that returns the pass has let model-controlled text set the score.
    """
    if t.single_token:
        # The judge produces exactly one token; there is no completion in which a quote precedes
        # the verdict, so the parser is fed the genuine verdict alone.
        completion = t.negative_verdict
    else:
        completion = f"{t.echo_prefix}{t.pass_fragment}\n{t.negative_verdict}"
    passed, verdict, note = _grade(t, completion, hardened)
    if passed:
        ev = (f"parser returned the quoted pass {verdict!r} although the judge's final verdict was "
              f"{t.negative_verdict.splitlines()[-1]!r}")
    else:
        ev = f"parser returned {verdict!r}: the judge's final verdict won"
        if t.single_token:
            ev += " (one-token verdict: nothing can precede it)"
        elif t.structured_output:
            ev += " (verdict is a typed structured-output field)"
    return {"open": passed, "evidence": ev,
            "details": {"completion": completion, "verdict": verdict, "echo_by_design": t.echo_by_design,
                        "structured_output": t.structured_output, "parser": note}}


def check_fail_mode(t: JudgeTemplate, hardened: bool = False) -> dict[str, Any]:
    """ETB-03: when the completion carries no usable verdict, what does the grader record?

    Two completions: empty, and a refusal sentence with no verdict token. Open if either is
    recorded as a pass.
    """
    outcomes: dict[str, dict[str, Any]] = {}
    for label, completion in (("empty", ""), ("refusal", "I cannot determine whether this is right.")):
        passed, verdict, _ = _grade(t, completion, hardened)
        outcomes[label] = {"verdict": verdict, "passed": passed}
    open_ = any(o["passed"] for o in outcomes.values())
    ev = ("a verdict-free completion is recorded as a pass" if open_
          else "verdict-free completions never pass: " + t.fail_mode_note)
    return {"open": open_, "evidence": ev, "details": {"outcomes": outcomes}}


def check_boundary_unescaped(t: JudgeTemplate, hardened: bool = False) -> dict[str, Any]:
    """ETB-02: can candidate text reproduce the template's own structural markers verbatim?

    Renders the template with a candidate that contains every marker the template uses and
    checks which survive into the prompt unchanged. Open if any does; the details list which.
    """
    candidate = "\n".join(f"{m} {CANARY}" for m in t.markers)
    rendered = t.render(candidate, hardened=hardened)
    baseline = t.render("", hardened=hardened)
    survived = []
    for m in t.markers:
        n_base = len(re.findall(re.escape(m), baseline, re.IGNORECASE))
        n_now = len(re.findall(re.escape(m), rendered, re.IGNORECASE))
        if n_now > n_base:
            survived.append(m)
    open_ = bool(survived)
    ev = (f"candidate text reproduces {len(survived)}/{len(t.markers)} structural markers verbatim: "
          f"{survived}" if open_
          else f"all {len(t.markers)} structural markers are neutralised or absent in the candidate")
    return {"open": open_, "evidence": ev,
            "details": {"survived": survived, "markers": list(t.markers),
                        "upstream_sanitizes": t.sanitizes is not None, "hardened_render": hardened}}


CHECKS: tuple[tuple[str, str, Callable[[JudgeTemplate, bool], dict[str, Any]]], ...] = (
    ("judge_echo_parse", "ETB-01", check_echo_parse),
    ("judge_fail_mode", "ETB-03", check_fail_mode),
    ("judge_boundary_unescaped", "ETB-02", check_boundary_unescaped),
)


def _run_check(fn: Callable[[JudgeTemplate, bool], dict[str, Any]], t: JudgeTemplate,
               hardened: bool) -> dict[str, Any]:
    try:
        return fn(t, hardened)
    except Exception as err:  # noqa: BLE001 - a check error is reported as undetermined, never aborts the run
        return {"open": None, "evidence": f"probe error: {type(err).__name__}: {err}", "details": {}}


def run_checks(spec: JudgeSpec) -> dict[str, Any]:
    """Run the three checks before and after hardening; the report is JSON-serialisable."""
    t = to_template(spec)
    rows: list[dict[str, Any]] = []
    for probe_id, etb, fn in CHECKS:
        row: dict[str, Any] = {"probe": probe_id, "etb": etb}
        for name, hardened in (("before", False), ("after", True)):
            row[name] = _run_check(fn, t, hardened)
        row["fix"] = FIXES[etb] if row["before"]["open"] else ""
        rows.append(row)
    return {
        "kind": "judge-check", "id": spec.id, "markers": t.markers, "placeholders": placeholders(spec.template),
        "parser": spec.parser, "rows": rows,
        "open_before": [r["etb"] for r in rows if r["before"]["open"]],
        "open_after": [r["etb"] for r in rows if r["after"]["open"]],
    }


def _state(x: dict[str, Any]) -> str:
    return "OPEN" if x["open"] else ("closed" if x["open"] is False else "undetermined")


def render_markdown(report: dict[str, Any]) -> str:
    marks = ", ".join("`" + m + "`" for m in report["markers"]) or "none found"
    lines = [f"# etbscan judge-check: {report['id']}", "",
             f"Markers checked: {marks}. Parser: {report['parser'].get('kind')}.", "",
             "| probe | class | as specified | hardened reading | what it means |", "|---|---|---|---|---|"]
    for r in report["rows"]:
        b, a = r["before"], r["after"]
        lines.append(f"| {r['probe']} | {r['etb']} | {_state(b)} | {_state(a)} | {b['evidence'][:220]} |")
    lines += ["", "## Fixes", ""]
    fixes = [f"- {r['etb']}: {r['fix']}" for r in report["rows"] if r["fix"]]
    lines += fixes or ["- nothing open as specified"]
    return "\n".join(lines) + "\n"


def main_judge_check(argv: list[str]) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="etbscan judge-check",
        description="Run the three judge-side checks (ETB-01 echo parse, ETB-03 fail mode, ETB-02 marker "
                    "boundary) against your own grading template, as specified and with the hardened "
                    "reading. No model is called.",
    )
    p.add_argument("--spec", required=True, type=Path,
                   help="JSON spec (YAML too when PyYAML is installed); fields documented in etbscan/judgecheck.py")
    p.add_argument("--out", type=Path, default=None, help="write judge-check.json and JUDGE-CHECK.md here")
    p.add_argument("--fail-on-open", action="store_true", help="exit 1 when any check is open as specified")
    a = p.parse_args(argv)
    try:
        spec = load_spec(a.spec)
    except (OSError, ValueError) as exc:
        print(f"etbscan judge-check: {exc}", file=sys.stderr)
        return 2
    report = run_checks(spec)
    md = render_markdown(report)
    print(md)
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "judge-check.json").write_text(json.dumps(report, indent=1, sort_keys=True, default=str),
                                                encoding="utf-8")
        (a.out / "JUDGE-CHECK.md").write_text(md, encoding="utf-8")
        print(f"wrote {a.out / 'judge-check.json'}")
    return 1 if a.fail_on_open and report["open_before"] else 0


__all__ = [
    "CHECKS",
    "FIXES",
    "JudgeSpec",
    "JudgeTemplate",
    "build_parsers",
    "check_boundary_unescaped",
    "check_echo_parse",
    "check_fail_mode",
    "derive_markers",
    "load_spec",
    "main_judge_check",
    "neutralize",
    "placeholders",
    "render_markdown",
    "run_checks",
    "to_template",
]
