"""Static lint for grader and verifier code: the ETB patterns that only code review finds.

The scanner proper measures ETB-01 by attacking a live judge. This module reads source instead,
for the classes that cannot be observed from outside the scoring code: how a verdict is parsed
out of judge text, how candidate text is spliced into a judge prompt, what a parse failure
defaults to, whether a test runner's exit status is used, and whether a verifier script restores
test files and runs its own Python safely. Every rule is a heuristic tuned for precision: it
fires on the shapes seen in real graders and stays silent when the safe shape is present
(last-match binding, anchors, escaping calls, `set -e`, `-I`/`PYTHONSAFEPATH`). The thresholds
were calibrated on a survey of 31 public evaluation frameworks (2026-11): a verdict regex must
name a verdict token, candidate-answer extraction is not a verdict parse, and a pass default
counts only where the value is returned or assigned in grading context. A finding is a place to
look, not a verdict; `# etbscan: ignore[RULE-ID]` on the line suppresses it.

    etbscan lint path/to/grader.py path/to/eval_scripts/
    etbscan lint . --json --fail-on high
"""

from __future__ import annotations

import ast
import json
import re
import warnings
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

from etbscan import __version__

SEVERITY = {"low": 0, "medium": 1, "high": 2}

# -- ETB-01 vocabulary -------------------------------------------------------------------------
# A regex literal is a verdict parse when it names a verdict token. "Strong" tokens make it one
# whatever text it is applied to; a bare letter class ([ABC], [A-D]) is "weak": it is also how a
# candidate's own multiple-choice answer is extracted for exact-match scoring.
_VERDICT_CI = re.compile(
    r"yes\|no|no\|yes|true\|false|false\|true"      # (yes|no), (true|false)
    r"|incorrect|correct\s*[:：]"                   # INCORRECT, "correct: yes"
    r"|\\\[\\\["                                     # [[n]], [[A]]
    r"|\b(?:score|rating|grade|verdict)s?\b",        # <score>, "Rating:", GRADE, "VERDICT:"
    re.IGNORECASE,
)
_VERDICT_CS = re.compile(
    r"\b[A-D]\|[A-D]\b"                              # (A|B|C)
    r"|\bCORRECT\b"
    r"|\b(?:PASS|PASSED|PASSES|PASSING|FAIL|FAILED|FAILS|FAILING)\b",
)
_PASS_WORD = re.compile(r"\bpass(?:ed|es|ing)?\b", re.IGNORECASE)
_FAIL_WORD = re.compile(r"\bfail(?:ed|s|ing|ure)?\b", re.IGNORECASE)
_COUNT_PASS_FAIL = re.compile(r"\\d.{0,12}?\b(?:pass|fail)(?:ed|es|ing)?\b", re.IGNORECASE)  # "(\d+)\s+passing"
_LETTER_CLASS = re.compile(r"\[A(?:-[B-J]|BC?D?)\]")                                           # [ABC], [A-D]
ANSWER_PHRASE = re.compile(r"answer is|final answer|the answer", re.IGNORECASE)
FILENAME_RE = re.compile(r"\\\.(?:jsonl?|txt|log|csv|ya?ml|md|py|html?)\b", re.IGNORECASE)
JUDGE_NAME = re.compile(r"judg|grad|annotat|evaluat|critique|verdict|rating|scor|review|assess", re.IGNORECASE)
CANDIDATE_NAME = re.compile(r"pred|answer|output|completion|generation|solution|submission", re.IGNORECASE)
LAST_MATCH_SHAPES = re.compile(r"^\(\?[a-z]*\)?\.\*(?!\?)|^\.\*(?!\?)|\$\s*$")  # greedy prefix or end anchor
INLINE_FLAGS = re.compile(r"^\(\?([a-zA-Z]+)\)")

# -- ETB-02 / ETB-03 vocabulary ----------------------------------------------------------------
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
# Names (of the enclosing function/class, the module, or the assignment target) that put a
# conditional expression in grading context. Config flags, file modes and fixtures live elsewhere.
GRADER_NAME = re.compile(
    r"grad(?:e|ing)|scor(?:e|ing)|judg|verdict|pars(?:e|ing)|evaluat|metric|reward|correct|pass(?!word)",
    re.IGNORECASE,
)
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


@dataclass
class LintReport:
    findings: list[Finding]
    files_scanned: int

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return dict(sorted(out.items()))

    def as_dict(self) -> dict:
        return {
            "tool": f"etb-scan {__version__} (etbscan lint)",
            "files_scanned": self.files_scanned,
            "counts": self.counts,
            "findings": [f.as_dict() for f in self.findings],
        }


def _ignored(source_line: str, rule: str) -> bool:
    m = re.search(r"etbscan:\s*ignore\[([^\]]+)\]", source_line)
    return bool(m and (rule in m.group(1).split(",") or "*" in m.group(1)))


# -- Python rules -----------------------------------------------------------------------------
class _PyLinter(ast.NodeVisitor):
    def __init__(self, path: str, source: str) -> None:
        self.path = path
        self.module_stem = Path(path).stem
        self.lines = source.splitlines()
        self.findings: list[Finding] = []
        self.compiled: dict[str, tuple[str, bool]] = {}  # name -> (pattern literal, MULTILINE) at module level
        self.module_has_escape = bool(ESCAPE_HINT.search(source))
        self.parents: dict[int, ast.AST] = {}
        self.scope: list[str] = []  # enclosing function and class names
        self._chain_members: set[int] = set()  # elif nodes already reported as part of a chain

    def _add(self, rule: str, cls: str, sev: str, line: int, msg: str, fix: str) -> None:
        src = self.lines[line - 1] if 0 < line <= len(self.lines) else ""
        if _ignored(src, rule):
            return
        self.findings.append(Finding(rule, cls, sev, self.path, line, msg, fix))

    def visit_Module(self, node: ast.Module) -> None:
        self.parents = {id(child): parent for parent in ast.walk(node) for child in ast.iter_child_nodes(parent)}
        for stmt in node.body:  # module-level compiled patterns
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                lit = _re_call_literal(stmt.value, "compile")
                if lit is not None:
                    for t in stmt.targets:
                        if isinstance(t, ast.Name):
                            self.compiled[t.id] = (lit, _multiline_flag(stmt.value))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]
    visit_ClassDef = visit_FunctionDef  # type: ignore[assignment]

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
        lit: str | None = None
        multiline = False
        is_match = False
        subject: ast.AST | None = None
        direct = _re_call_literal(node, "search")
        if direct is None:
            direct = _re_call_literal(node, "match")
            is_match = direct is not None
        if direct is not None:  # re.search(r"...", text)
            lit, multiline = direct, _multiline_flag(node)
            subject = node.args[1] if len(node.args) > 1 else _kwarg(node, "string")
        elif isinstance(node.func, ast.Attribute) and node.func.attr in ("search", "match"):
            is_match = node.func.attr == "match"
            if isinstance(node.func.value, ast.Name) and node.func.value.id in self.compiled:  # PAT.search(text)
                lit, multiline = self.compiled[node.func.value.id]
                subject = node.args[0] if node.args else _kwarg(node, "string")
            elif node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in self.compiled:
                lit, multiline = self.compiled[node.args[0].id]  # re.search(PAT, text)
                multiline = multiline or _multiline_flag(node)
                subject = node.args[1] if len(node.args) > 1 else _kwarg(node, "string")
        if lit is None:
            return
        strength = _verdict_tokens(lit)
        if strength is None or FILENAME_RE.search(lit):
            return  # no verdict token at all (PASSWORD, "Failed password"), or a file-name regex
        if LAST_MATCH_SHAPES.search(lit) or _positionally_bound(lit, is_match, multiline):
            return
        name = _expr_name(subject) if subject is not None else ""
        candidate = bool(CANDIDATE_NAME.search(name) and not JUDGE_NAME.search(name)) or bool(ANSWER_PHRASE.search(lit))
        if strength == "weak" and candidate:
            return  # the candidate's own answer letter being extracted for exact match, not a judge verdict
        self._add("ETB-01-FIRST-MATCH", "ETB-01", "high", node.lineno,
                  f"verdict taken from the FIRST match of {lit!r} in judge text; an earlier quoted or injected "
                  f"token wins over the judge's final verdict",
                  "bind to the last well-formed verdict (findall(...)[-1], a greedy (?s).* prefix, or a line anchor) "
                  "and validate it against the offered grades")

    # ETB-01: fixed-order substring chain, reported once at the head of the chain
    def _check_substring_order(self, node: ast.If) -> None:
        if id(node) in self._chain_members:
            return
        labels = []
        cur: ast.AST | None = node
        while isinstance(cur, ast.If):
            t = cur.test
            if (isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.In)
                    and isinstance(t.left, ast.Constant) and isinstance(t.left.value, str)
                    and VERDICT_LABEL.match(t.left.value)):
                labels.append(t.left.value)
                if cur is not node:
                    self._chain_members.add(id(cur))
            else:
                break
            cur = cur.orelse[0] if len(cur.orelse) == 1 else None
        if len(labels) >= 2:
            self._add("ETB-01-SUBSTRING-ORDER", "ETB-01", "high", node.lineno,
                      f"verdict decided by substring presence in a fixed order {labels}; a label that merely "
                      f"appears earlier (quoted from the candidate) beats the final one",
                      "pick the label that occurs last in the judgment, or parse an anchored final line")

    # ETB-03: parse failure defaults to a pass, in grading context
    def _check_default_pass(self, node: ast.IfExp) -> None:
        if not isinstance(node.orelse, ast.Constant):
            return
        v = node.orelse.value
        if not ((isinstance(v, str) and v.strip().lower() in PASS_DEFAULTS) or v is True):
            return
        if isinstance(node.body, ast.Constant):
            return  # `False if flag else True` maps a boolean to constants; nothing was parsed and defaulted
        is_value, target = self._value_context(node)
        if not is_value:
            return  # subscript index, comprehension element, assert, f-string: the value is not a verdict
        context = " ".join([target, *self.scope, self.module_stem])
        if not GRADER_NAME.search(context):
            return
        self._add("ETB-03-DEFAULT-PASS", "ETB-03", "high", node.lineno,
                  f"no verdict found defaults to {v!r}, which reads as a pass",
                  "default to unscored or fail and surface the parse failure")

    def _value_context(self, node: ast.AST) -> tuple[bool, str]:
        """Whether `node` is the value of a return, assignment, keyword, dict entry or call argument,
        and the name that value flows into (empty when positional)."""
        cur = node
        while True:
            parent = self.parents.get(id(cur))
            if parent is None:
                return False, ""
            if isinstance(parent, (ast.IfExp, ast.Await)) and getattr(parent, "test", None) is not cur:
                cur = parent  # nested ternary / awaited: same destination as the outer expression
                continue
            if isinstance(parent, ast.Return) and parent.value is cur:
                return True, ""
            if isinstance(parent, ast.Lambda) and parent.body is cur:
                return True, ""
            if isinstance(parent, ast.Assign) and parent.value is cur:
                return True, " ".join(_target_name(t) for t in parent.targets)
            if isinstance(parent, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) and parent.value is cur:
                return True, _target_name(parent.target)
            if isinstance(parent, ast.keyword):
                return True, parent.arg or ""
            if isinstance(parent, ast.Dict):
                for k, val in zip(parent.keys, parent.values):
                    if val is cur:
                        return True, k.value if isinstance(k, ast.Constant) and isinstance(k.value, str) else ""
                return False, ""
            if isinstance(parent, ast.Call) and any(a is cur for a in parent.args):
                return True, ""
            return False, ""

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


def _kwarg(node: ast.Call, name: str) -> ast.AST | None:
    for k in node.keywords:
        if k.arg == name:
            return k.value
    return None


def _multiline_flag(call: ast.Call) -> bool:
    """re.M / re.MULTILINE anywhere in the call's flag arguments."""
    for n in [*call.args[1:], *(k.value for k in call.keywords)]:
        for sub in ast.walk(n):
            if isinstance(sub, ast.Attribute) and sub.attr in ("M", "MULTILINE"):
                return True
    return False


def _expr_name(node: ast.AST) -> str:
    """Dotted name of the expression a regex is applied to: `grading_response.completion`, `pred`."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_expr_name(node.value)}.{node.attr}"
    if isinstance(node, (ast.Call, ast.Subscript)):
        return _expr_name(node.func if isinstance(node, ast.Call) else node.value)
    return ""


def _target_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, (ast.Tuple, ast.List)):
        return " ".join(_target_name(e) for e in node.elts)
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return node.slice.value  # results["score"] = ...
    return ""


def _verdict_tokens(lit: str) -> str | None:
    """'strong' when the regex names a verdict (yes|no, A|B|C, PASS|FAIL, score/grade tags, [[n]]),
    'weak' for a bare letter class, None when it contains no verdict token at all."""
    if (_VERDICT_CI.search(lit) or _VERDICT_CS.search(lit) or _COUNT_PASS_FAIL.search(lit)
            or (_PASS_WORD.search(lit) and _FAIL_WORD.search(lit))):
        return "strong"
    if _LETTER_CLASS.search(lit):
        return "weak"
    return None


def _positionally_bound(lit: str, is_match: bool, multiline: bool) -> bool:
    """A `^`/`\\A` anchor (or re.match) binds the parse to the start of the text, so nothing earlier can
    win; a lazy `.*?` right after it, or MULTILINE with `^`, makes it a first match again."""
    m = INLINE_FLAGS.match(lit)
    body = lit[m.end():] if m else lit
    if m and "m" in m.group(1):
        multiline = True
    if body.startswith("\\A"):
        after, defeated = body[2:], False
    elif body.startswith("^"):
        after, defeated = body[1:], multiline
    elif is_match:
        after, defeated = body, False
    else:
        return False
    if after.startswith((".*?", "[\\s\\S]*?", "(.*?)")):
        return False
    return not defeated


# -- Shell rules -------------------------------------------------------------------------------
_SHA = r"[0-9a-f]{7,40}|HEAD|[A-Za-z_][\w./-]*"
GIT_CHECKOUT_PATHS = re.compile(rf"^\s*git checkout ({_SHA}) (?!--)(\S+\s+\S+.*)$")
GIT_CHECKOUT_SWALLOWED = re.compile(r"\bgit checkout\s+(?P<args>[^|&;]*?)\|\|(?P<handler>.*)$")
SWALLOW_HANDLER = re.compile(r"^\s*(?:true|:|continue|echo\b[^;&|]*|printf\b[^;&|]*)\s*(?:;;|;|fi|done|\})?\s*$")
GIT_APPLY = re.compile(r"^\s*git apply\b(?!.*\|\|)(?!.*&&)")
CD_LINE = re.compile(r"^\s*cd\s+\S+")
PY_FROM_CWD = re.compile(r"\bpython3?\s+(-\s*(<<|$)|-c\b|<<)")
EXIT_CAPTURE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)=\$\?\s*$")


def _swallowed_restore(line: str) -> bool:
    """`git checkout <ref> -- <path> 2>/dev/null || true`: a per-path restore whose failure is discarded."""
    m = GIT_CHECKOUT_SWALLOWED.search(line)
    if not m:
        return False
    args = m.group("args").split()
    if any(a in ("-b", "-B", "--orphan", "--detach") for a in args):
        return False  # branch switching, not a restore
    toks = [a for a in args if not a.startswith(("2>", ">", "<", "&>", "-q", "--quiet", "-f", "--force"))]
    if "--" not in toks and len(toks) < 2:
        return False  # `git checkout main || true`
    return bool(SWALLOW_HANDLER.match(m.group("handler")))


def _lint_shell(path: str, text: str) -> list[Finding]:
    out: list[Finding] = []
    lines = text.splitlines()
    set_e = any(re.match(r"^\s*set\s+-[a-zA-Z]*e", ln) for ln in lines)
    safe_path = "PYTHONSAFEPATH" in text or re.search(r"\bpython3?\s+-[IP]\b", text) is not None
    seen_cd = False
    for i, ln in enumerate(lines, 1):
        if CD_LINE.match(ln):
            seen_cd = True
        swallowed = _swallowed_restore(ln)
        if swallowed and not _ignored(ln, "ETB-11-RESTORE-FAILS-OPEN"):
            out.append(Finding("ETB-11-RESTORE-FAILS-OPEN", "ETB-11", "medium", path, i,
                               "per-path restore `git checkout <ref> -- <path> || true` swallows the failure: a test "
                               "file the graded program deleted, replaced with a directory or otherwise made "
                               "unrestorable stays as the program left it and the run continues; this fails open "
                               "per file even under `set -e`",
                               "fail closed (`|| { echo RESTORE_FAILED <path>; exit 1; }`), delete paths that do not "
                               "exist at <ref> instead of ignoring the error, and check `git status --porcelain` on "
                               "the test paths before running the tests"))
        if not set_e:
            m = GIT_CHECKOUT_PATHS.match(ln)
            if m and not swallowed and not _ignored(ln, "ETB-11-RESTORE-FAILS-OPEN"):
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
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)  # the linted file's escape hygiene is not our finding
                tree = ast.parse(text)
        except (SyntaxError, ValueError):
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


def run_lint(paths: Iterable[str]) -> LintReport:
    findings: list[Finding] = []
    scanned = 0
    for f in iter_files(paths):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        findings.extend(lint_source(str(f), text))
    return LintReport(findings, scanned)


def lint_paths(paths: Iterable[str]) -> list[Finding]:
    return run_lint(paths).findings


def render(findings: list[Finding], files_scanned: int | None = None) -> str:
    scanned = f" ({files_scanned} file(s) scanned)" if files_scanned is not None else ""
    if not findings:
        return f"etbscan lint: no findings{scanned}"
    lines = []
    for f in findings:
        lines.append(f"{f.path}:{f.line}: {f.rule} [{f.etb_class}, {f.severity}] {f.message}")
        lines.append(f"    fix: {f.fix}")
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    where = f" in {files_scanned} file(s) scanned" if files_scanned is not None else ""
    lines.append(f"etbscan lint: {len(findings)} finding(s){where}: "
                 + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return "\n".join(lines)


def main_lint(argv: list[str]) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="etbscan lint",
                                description="Static lint for grader and verifier code (ETB-01/02/03/09/11 patterns).")
    p.add_argument("paths", nargs="+")
    p.add_argument("--json", action="store_true",
                   help="emit a JSON object: tool, files_scanned, counts by severity, findings")
    p.add_argument("--fail-on", choices=sorted(SEVERITY, key=SEVERITY.get), default="high",
                   help="exit 1 when a finding at or above this severity exists (default high)")
    a = p.parse_args(argv)
    report = run_lint(a.paths)
    print(json.dumps(report.as_dict(), indent=2) if a.json else render(report.findings, report.files_scanned))
    threshold = SEVERITY[a.fail_on]
    return 1 if any(SEVERITY[f.severity] >= threshold for f in report.findings) else 0
