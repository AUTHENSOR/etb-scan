"""Static lint: fires on the grader shapes seen in the wild, stays quiet on the safe shapes."""
from etbscan.lint import lint_source, render

FIRST_MATCH = '''
import re
def grade(resp):
    match = re.search(r"correct: (yes|no)", resp)
    return match.group(0) if match else "no"
def letter(resp):
    m = re.search(r"(A|B|C)", resp)
    return m.group(0) if m else "C"
'''
LAST_MATCH = '''
import re
PAT = r"(?is).*(?<!\\w)GRADE(?!\\w)\\s*:\\s*([CPI])"
def grade(resp):
    m = re.search(PAT, resp)
    return m.group(1) if m else None
def grade2(resp):
    ms = re.findall(r"correct: (yes|no)", resp)
    return ms[-1] if ms else "no"
'''
SUBSTRING = '''
def winner(judgment):
    if "[[A]]" in judgment:
        return "A"
    elif "[[B]]" in judgment:
        return "B"
    elif "[[C]]" in judgment:
        return "tie"
    return "error"
'''
DEFAULT_PASS = '''
import re
def grade(resp):
    m = re.findall(r"^verdict: (pass|fail)$", resp)
    return m[-1] if m else "pass"
'''
SPLICE = '''
TEMPLATE = """Judge the [response] to the [question].

[question]: {question}

[response]: {response}

correct: Answer yes or no."""
def prompt(q, r):
    return TEMPLATE.format(question=q, response=r)
'''
SPLICE_ESCAPED = SPLICE + '''
def neutralize(text):
    return text.replace("[response]:", "[response] :")
'''
CHAINED = '''
def build(convo, rubric):
    return TEMPLATE.replace("<<conversation>>", convo).replace("<<rubric_item>>", rubric)
TEMPLATE = "x <<conversation>> y <<rubric_item>>"
'''
EVAL_SCRIPT = """#!/bin/bash
set -uxo pipefail
cd /testbed
git checkout dd1615c59dc6fff633e27dbb3861f2d27e1fb976 tests/roots/new_file.py tests/test_mod.py
git apply -v - <<'EOF_1'
diff --git a/tests/test_mod.py b/tests/test_mod.py
EOF_1
: '>>>>> Start Test Output'
tox -e py39 -- tests/test_mod.py
SWEBENCH_TEST_EXIT_CODE=$?
: '>>>>> End Test Output'
echo "exit: $SWEBENCH_TEST_EXIT_CODE"
"""
VERIFIER = """#!/bin/bash
set -uo pipefail
cd /app 2>/dev/null || cd /testbed
python3 - <<'PYRESET'
import subprocess
PYRESET
bash /tests/run_script.sh > out.txt 2> err.txt
RUN_EXIT_CODE=$?
python3 << 'EVAL_EOF'
import json
EVAL_EOF
"""
RUN_SCRIPT = """#!/bin/bash
set -e
go test -v ./internal/config || true
pytest tests -v || true
"""
SAFE_SCRIPT = """#!/bin/bash
set -euo pipefail
cd /app
export PYTHONSAFEPATH=1
python3 - <<'X'
print(1)
X
git checkout abc1234 -- tests/a.py
go test -v ./... | tee out.txt
"""


def rules(src, name):
    return sorted({f.rule for f in lint_source(name, src)})


def test_first_match_fires_and_last_match_does_not():
    assert rules(FIRST_MATCH, "g.py") == ["ETB-01-FIRST-MATCH"]
    assert len(lint_source("g.py", FIRST_MATCH)) == 2
    assert rules(LAST_MATCH, "g.py") == []


def test_substring_order_and_default_pass():
    assert rules(SUBSTRING, "g.py") == ["ETB-01-SUBSTRING-ORDER"]
    assert rules(DEFAULT_PASS, "g.py") == ["ETB-03-DEFAULT-PASS"]


def test_splice_fires_only_without_escaping_and_chained_replace():
    assert rules(SPLICE, "g.py") == ["ETB-02-UNESCAPED-SPLICE"]
    assert rules(SPLICE_ESCAPED, "g.py") == []
    assert rules(CHAINED, "g.py") == ["ETB-02-CHAINED-REPLACE"]


def test_shell_rules():
    assert rules(EVAL_SCRIPT, "eval.sh") == ["ETB-11-APPLY-UNCHECKED", "ETB-11-RESTORE-FAILS-OPEN"]
    assert rules(VERIFIER, "test.sh") == ["ETB-09-EXIT-UNUSED", "ETB-11-REPO-RELATIVE-PYTHON"]
    assert len([f for f in lint_source("test.sh", VERIFIER) if f.rule == "ETB-11-REPO-RELATIVE-PYTHON"]) == 2
    assert rules(RUN_SCRIPT, "run.sh") == ["ETB-09-EXIT-IGNORED"]
    assert rules(SAFE_SCRIPT, "safe.sh") == []


def test_ignore_comment_and_render(tmp_path):
    src = FIRST_MATCH.replace('re.search(r"(A|B|C)", resp)', 're.search(r"(A|B|C)", resp)  # etbscan: ignore[ETB-01-FIRST-MATCH]')
    fs = lint_source("g.py", src)
    assert len(fs) == 1
    text = render(fs)
    assert "ETB-01-FIRST-MATCH" in text and "fix:" in text and "1 finding(s)" in text
    assert render([]) == "etbscan lint: no findings"


def test_cli_exit_codes(tmp_path):
    from etbscan.__main__ import main
    f = tmp_path / "g.py"; f.write_text(FIRST_MATCH)
    assert main(["lint", str(f)]) == 1
    assert main(["lint", str(f), "--fail-on", "high", "--json"]) == 1
    ok = tmp_path / "ok.py"; ok.write_text(LAST_MATCH)
    assert main(["lint", str(ok)]) == 0
