"""Static lint for grader and verifier code: the ETB patterns that only code review finds.

The scanner proper measures ETB-01 by attacking a live judge. This module reads source instead,
for the classes that cannot be observed from outside the scoring code: how a verdict is parsed
out of judge text, how candidate text is spliced into a judge prompt, what a parse failure
defaults to, whether a test runner's exit status is used, and whether a verifier script restores
test files and runs its own Python safely. Every rule is a heuristic tuned for precision: it
fires on the shapes seen in real graders and stays silent when the safe shape is present
(last-match binding, anchors, escaping calls, `set -e`, `-I`/`PYTHONSAFEPATH`). A finding is a
place to look, not a verdict; `# etbscan: ignore[RULE-ID]` on the line suppresses it.

    etbscan lint path/to/grader.py path/to/eval_scripts/
    etbscan lint . --json --fail-on high
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

SEVERITY = {"low": 0, "medium": 1, "high": 2}

VERDICT_VOCAB = re.compile(
    r"\(yes\|no\)|\(A\|B\|C\)|\[ABC\]|\[A-D\]|\\\[\\\[|GRADE|correct|PASS|FAIL|rating|score|verdict",
    re.IGNORECASE,
)
LAST_MATCH_SHAPES = re.compile(r"^\(\?[a-z]*\)?\.\*|^\.\*|\$\s*$")  # greedy prefix or end anchor
CANDIDATE_FIELDS = {
    "answer", "answers", "response", "responses", "output", "outputs", "completion", "conversation",
    "submission", "prediction", "predicted_answer", "answer_a", "answer_b", "output_1", "output_2",
    "ANSWER_A", "ANSWER_B", "model_output", "candidate", "transcript",
}
PROMPT_MARKERS = (
    "[The Start of", "[The End of", "<|", "[BEGIN DATA]", "[END DATA]", "***", "###", '"""',
    "[response]:", "[Submission]:", "[question]:", "Predicted answer:", "Gold target:",
    "# Conversation", "# Rubric", "<<", ">>",
)
ESCAPE_HINT = re.compile(r"escape|sanitiz|neutrali[sz]|delimit|strip_markers|quote", re.IGNORECASE)
PASS_DEFAULTS = {"yes", "correct: yes", "a", "pass", "passed", "true", "correct"}
VERDICT_LABEL = re.compile(r"^\[\[[A-C]\]\]$|^(PASS|FAIL|CORRECT|INCORRECT|yes|no|YES|NO|TRUE|FALSE)$")
TEST_RUNNER = re.compile(
    r"\b(pytest|py\.test|go test|npm test|yarn test|pnpm test|npx jest|jest|mocha|vitest|cargo test|tox\b|"
    r"runtests\.py|bin/test|unittest|ctest|mvn test|gradle test)",
)
SHELL_SUFFIXES = {".sh", ".bash"}
PY_SUFFIXES = {".py"}


@dataclass(frozen=True)
class Finding:
    rule: str
    etb_class: str
    severity: str
    path: str
    line: int
    message: str
    fix: str

    def as_dict(self) -> dict:
        return asdict(self)


def _ignored(source_line: str, rule: str) -> bool:
    m = re.search(r"etbscan:\s*ignore\[([^\]]+)\]", source_line)
    return bool(m and (rule in m.group(1).split(",") or "*" in m.group(1)))


# -- Python rules -----------------------------------------------------------------------------
class _PyLinter(ast.NodeVisitor):
    def __init__(self, path: str, source: str) -> None:
        self.path = path
        self.lines = source.splitlines()
        self.findings: list[Finding] = []
        self.compiled: dict[str, str] = {}  # name -> pattern literal for re.compile at module level
        self.module_has_escape = bool(ESCAPE_HINT.search(source))

    def _add(self, rule: str, cls: str, sev: str, line: int, msg: str, fix: str) -> None:
        src = self.lines[line - 1] if 0 < line <= len(self.lines) else ""
        if _ignored(src, rule):
            return
        self.findings.append(Finding(rule, cls, sev, self.path, line, msg, fix))

    def visit_Module(self, node: ast.Module) -> None:
        for stmt in node.body:  # module-level compiled patterns
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                lit = _re_call_literal(stmt.value, "compile")
                if lit is not None:
                    for t in stmt.targets:
                        if isinstance(t, ast.Name):
                            self.compiled[t.id] = lit
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        self._check_first_match(node)
        self._check_splice_call(node)
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self._check_substring_order(node)
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._check_default_pass(node)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and len(node.value) > 40:
            self._check_template_literal(node)

    # ETB-01: first-match verdict extraction
    def _check_first_match(self, node: ast.Call) -> None:
        lit = _re_call_literal(node, "search") or _re_call_literal(node, "match")
        if lit is None and isinstance(node.func, ast.Attribute) and node.func.attr in ("search", "match"):
            if isinstance(node.func.value, ast.Name) and node.func.value.id in self.compiled:
                lit = self.compiled[node.func.value.id]
            elif node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in self.compiled:
                lit = self.compiled[node.args[0].id]
        if lit is None or not VERDICT_VOCAB.search(lit) or LAST_MATCH_SHAPES.search(lit):
            return
        self._add("ETB-01-FIRST-MATCH", "ETB-01", "high", node.lineno,
                  f"verdict taken from the FIRST match of {lit!r} in judge text; an earlier quoted or injected "
                  f"token wins over the judge's final verdict",
                  "bind to the last well-formed verdict (findall(...)[-1], a greedy (?s).* prefix, or a line anchor) "
                  "and validate it against the offered grades")

    # ETB-01: fixed-order substring chain
    def _check_substring_order(self, node: ast.If) -> None:
        labels = []
        cur: ast.AST | None = node
        while isinstance(cur, ast.If):
            t = cur.test
            if (isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.In)
                    and isinstance(t.left, ast.Constant) and isinstance(t.left.value, str)
                    and VERDICT_LABEL.match(t.left.value)):
                labels.append(t.left.value)
            else:
                break
            cur = cur.orelse[0] if len(cur.orelse) == 1 else None
        if len(labels) >= 2:
            self._add("ETB-01-SUBSTRING-ORDER", "ETB-01", "high", node.lineno,
                      f"verdict decided by substring presence in a fixed order {labels}; a label that merely "
                      f"appears earlier (quoted from the candidate) beats the final one",
                      "pick the label that occurs last in the judgment, or parse an anchored final line")

    # ETB-03: parse failure defaults to a pass
    def _check_default_pass(self, node: ast.IfExp) -> None:
        if isinstance(node.orelse, ast.Constant):
            v = node.orelse.value
            if (isinstance(v, str) and v.strip().lower() in PASS_DEFAULTS) or v is True:
                self._add("ETB-03-DEFAULT-PASS", "ETB-03", "high", node.lineno,
                          f"no verdict found defaults to {v!r}, which reads as a pass",
                          "default to unscored or fail and surface the parse failure")

    # ETB-02: template literal with candidate placeholder and structural markers, no escaping in module
    def _check_template_literal(self, node: ast.Constant) -> None:
        text = node.value
        fields = set(re.findall(r"\{(\w+)\}", text)) | set(re.findall(r"<<(\w+)>>", text))
        if not (fields & CANDIDATE_FIELDS):
            return
        markers = [m for m in PROMPT_MARKERS if m in text]
        if not markers or self.module_has_escape:
            return
        self._add("ETB-02-UNESCAPED-SPLICE", "ETB-02", "medium", node.lineno,
                  f"judge prompt splices candidate field(s) {sorted(fields & CANDIDATE_FIELDS)} next to structural "
                  f"markers {markers[:4]} and this module never escapes or neutralises candidate text",
                  "fence candidate text in a unique delimiter and neutralise the template's own markers inside it "
                  "before formatting")

    def _check_splice_call(self, node: ast.Call) -> None:
        # str.replace("<<conversation>>", x).replace("<<rubric>>", y): second pass re-expands placeholders
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "replace"
                and isinstance(node.func.value, ast.Call) and isinstance(node.func.value.func, ast.Attribute)
                and node.func.value.func.attr == "replace"):
            first = node.func.value.args[0] if node.func.value.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and "<<" in first.value:
                self._add("ETB-02-CHAINED-REPLACE", "ETB-02", "low", node.lineno,
                          "chained str.replace substitution: a placeholder literal inside the first inserted text "
                          "is expanded by the second replace",
                          "substitute every placeholder in one pass (re.sub with a lookup) or use a template engine")


def _re_call_literal(node: ast.Call, name: str) -> str | None:
    f = node.func
    is_re = (isinstance(f, ast.Attribute) and f.attr == name and isinstance(f.value, ast.Name)
             and f.value.id in ("re", "regex"))
    if not is_re or not node.args:
        return None
    a = node.args[0]
    return a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else None


# -- Shell rules -------------------------------------------------------------------------------
_SHA = r"[0-9a-f]{7,40}|HEAD|[A-Za-z_][\w./-]*"
GIT_CHECKOUT_PATHS = re.compile(rf"^\s*git checkout ({_SHA}) (?!--)(\S+\s+\S+.*)$")
GIT_APPLY = re.compile(r"^\s*git apply\b(?!.*\|\|)(?!.*&&)")
CD_LINE = re.compile(r"^\s*cd\s+\S+")
PY_FROM_CWD = re.compile(r"\bpython3?\s+(-\s*(<<|$)|-c\b|<<)")
EXIT_CAPTURE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)=\$\?\s*$")


def _lint_shell(path: str, text: str) -> list[Finding]:
    out: list[Finding] = []
    lines = text.splitlines()
    set_e = any(re.match(r"^\s*set\s+-[a-zA-Z]*e", ln) for ln in lines)
    safe_path = "PYTHONSAFEPATH" in text or re.search(r"\bpython3?\s+-[IP]\b", text) is not None
    seen_cd = False
    for i, ln in enumerate(lines, 1):
        if CD_LINE.match(ln):
            seen_cd = True
        if not set_e:
            m = GIT_CHECKOUT_PATHS.match(ln)
            if m and not _ignored(ln, "ETB-11-RESTORE-FAILS-OPEN"):
                out.append(Finding("ETB-11-RESTORE-FAILS-OPEN", "ETB-11", "high", path, i,
                                   "multi-path `git checkout <ref> <paths>` without `--` in a script that does not stop "
                                   "on error: one path missing at <ref> fails the whole restore and nothing is restored",
                                   "restore only paths that exist at <ref>, delete the rest, and fail closed when the "
                                   "restore or the following patch apply fails"))
            if GIT_APPLY.match(ln) and not _ignored(ln, "ETB-11-APPLY-UNCHECKED"):
                out.append(Finding("ETB-11-APPLY-UNCHECKED", "ETB-11", "medium", path, i,
                                   "`git apply` result is not checked and the script does not stop on error: tests run "
                                   "on whatever is in the tree when the patch fails",
                                   "append `|| exit 1` (or echo a failure marker the grader treats as failed)"))
        if seen_cd and not safe_path and PY_FROM_CWD.search(ln) and not _ignored(ln, "ETB-11-REPO-RELATIVE-PYTHON"):
            out.append(Finding("ETB-11-REPO-RELATIVE-PYTHON", "ETB-11", "high", path, i,
                               "Python started from stdin or -c after `cd` into the graded repository: sys.path[0] is "
                               "the working directory, so a repository file named like a standard module shadows it",
                               "export PYTHONSAFEPATH=1 (3.11+), run helpers as files with `python3 -I`, or cd elsewhere"))
        if TEST_RUNNER.search(ln) and re.search(r"\|\|\s*true\s*$", ln) and not _ignored(ln, "ETB-09-EXIT-IGNORED"):
            out.append(Finding("ETB-09-EXIT-IGNORED", "ETB-09", "medium", path, i,
                               "test runner's exit status discarded with `|| true`; grading must then rely on parsing "
                               "the run's text, which the program under test can print",
                               "keep the exit status and combine it with a runner-generated report (junit, go test -json)"))
        m = EXIT_CAPTURE.match(ln)
        if m and not _ignored(ln, "ETB-09-EXIT-UNUSED"):
            var = m.group(1)
            used = any(f"${var}" in other or f"${{{var}}}" in other for j, other in enumerate(lines, 1) if j != i)
            if not used:
                out.append(Finding("ETB-09-EXIT-UNUSED", "ETB-09", "medium", path, i,
                                   f"exit status captured into {var} and never read",
                                   "use it in the verdict (fail when non-zero and no required test is reported)"))
    return out


# -- driver ------------------------------------------------------------------------------------
def lint_source(path: str, text: str) -> list[Finding]:
    suffix = Path(path).suffix.lower()
    if suffix in PY_SUFFIXES:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        v = _PyLinter(path, text)
        v.visit(tree)
        return v.findings
    if suffix in SHELL_SUFFIXES or text.startswith(("#!/bin/bash", "#!/bin/sh", "#!/usr/bin/env bash")):
        return _lint_shell(path, text)
    return []


def iter_files(paths: Iterable[str]) -> Iterator[Path]:
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            for f in sorted(pp.rglob("*")):
                if f.is_file() and f.suffix.lower() in PY_SUFFIXES | SHELL_SUFFIXES and ".venv" not in f.parts \
                        and "node_modules" not in f.parts and ".git" not in f.parts:
                    yield f
        elif pp.is_file():
            yield pp


def lint_paths(paths: Iterable[str]) -> list[Finding]:
    out: list[Finding] = []
    for f in iter_files(paths):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.extend(lint_source(str(f), text))
    return out


def render(findings: list[Finding]) -> str:
    if not findings:
        return "etbscan lint: no findings"
    lines = []
    for f in findings:
        lines.append(f"{f.path}:{f.line}: {f.rule} [{f.etb_class}, {f.severity}] {f.message}")
        lines.append(f"    fix: {f.fix}")
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    lines.append(f"etbscan lint: {len(findings)} finding(s): " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return "\n".join(lines)


def main_lint(argv: list[str]) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="etbscan lint",
                                description="Static lint for grader and verifier code (ETB-01/02/03/09/11 patterns).")
    p.add_argument("paths", nargs="+")
    p.add_argument("--json", action="store_true")
    p.add_argument("--fail-on", choices=sorted(SEVERITY, key=SEVERITY.get), default="high",
                   help="exit 1 when a finding at or above this severity exists (default high)")
    a = p.parse_args(argv)
    findings = lint_paths(a.paths)
    print(json.dumps([f.as_dict() for f in findings], indent=2) if a.json else render(findings))
    threshold = SEVERITY[a.fail_on]
    return 1 if any(SEVERITY[f.severity] >= threshold for f in findings) else 0
