"""Static lint: fires on the grader shapes seen in the wild, stays quiet on the safe shapes."""
import json

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


# -- calibration against the 2026-11 ecosystem survey (31 public eval frameworks) --------------
# Every confirmed ETB-01-FIRST-MATCH hit in the survey, one per distinct shape: these must keep firing.
CONFIRMED_FIRST_MATCH = r'''
import re
one_score_pattern = re.compile(r"\[\[(\d+\.?\d*)\]\]")
two_score_pattern = re.compile(r"\[\[(\d+\.?\d*),\s?(\d+\.?\d*)\]\]")
def browsecomp(grading_response):                                   # simple-evals / HLE
    return re.search(r"correct: (yes|no)", grading_response)
def simpleqa(grading_response):                                     # simple-evals
    return re.search(r"(A|B|C)", grading_response)
def inspect_browse_comp(grading_response):                          # inspect_evals copy
    return re.search(r"correct: (yes|no)", grading_response.completion)
def frontierscience(response_text):
    return re.search(r"VERDICT:\s*([\d.]+)", response_text, re.IGNORECASE)
def inspect_simpleqa(raw_grade, paper):
    if paper:
        return re.search(r"(A|B|C)", raw_grade)
    return re.search(r"\b([ABC])\b", raw_grade)
def helm(annotator_response_text):                                  # model_as_judge + 5 annotators
    return re.search(r"<\s*score\s*>(.*?)<\/?\s*score\s*>", annotator_response_text, re.DOTALL | re.IGNORECASE)
def vibe(evaluator_response):
    return re.search(r"Rating:\s*([1-5])", evaluator_response)
def lighteval(response, x):
    a = re.search(r"\[\[(\d.\d)\]\]", response)
    b = re.search(r"<score>\s(\d)\s</score>", x)
    c = re.search(r"\[\[([01])\]\]", x)
    return a, b, c
def fastchat(judgment):                                             # MT-bench common.py
    return re.search(one_score_pattern, judgment) or re.search(two_score_pattern, judgment)
def clbench(text):
    return re.search(r'"?Overall Score"?\s*[:：]\s*"?([01])', text)
def visual_judge(text):
    return re.search(r"\[FINAL SCORE\]: (\d{1,3})", text)
def harbor_simpleqa(response_text):
    return re.search(r"(A|B|C)", response_text.upper())
def hardhat(content):                                               # preparedness evmbench fallback
    return re.search(r"(\d+)\s+passing", content), re.search(r"(\d+)\s+failing", content)
'''
# The 23 false positives: candidate-answer extraction for exact match, and regexes that merely
# contain a verdict-looking substring (PASSWORD, "Failed password", scores_*.json, vim setreg).
NOISE_FIRST_MATCH = r'''
import re
_SENSITIVE_KEY_RE = re.compile(r"(?i)(PASSWORD|SECRET|TOKEN|API_KEY)")
def is_sensitive(key):
    return bool(_SENSITIVE_KEY_RE.search(key))
def minerva(text):
    return re.search("Final Answer: The final answer is(.*?). I hope it is correct.", text)
def putnam(text):
    return re.search(r"(?:Final Answer: The final answer is|The answer is:)\s*(.*?)(?=I hope it is correct\.)", text)
def gpqa(output_text):
    m = re.search(r"correct answer is [^A-Za-z]*([A-J])", output_text)
    return m or re.search(r"correct answer is [^A-Z]*([A-J])", output_text)
def infinitebench(pred):
    return re.search(r"\b([A-D])\b(?!.*\b[A-D]\b)", pred)
def quarto_summary(line):
    return re.search("passed", line) and re.search("failed", line) and re.search("steps", line)
def rationale(text):
    return re.search(r'"?Grading Rationale"?\s*[:：]\s*"?(.*?)"?\s*,', text, re.DOTALL)
def side_task(task_metadata):
    return re.search(r"PasswordLock_(.+)", task_metadata.side_task_name)
def test_intrusion_report(content):
    assert re.search(r"(Failed password|GET /admin|GET /phpmyadmin)", content)
def vim_registers(line):
    if re.match(r"^:?call setreg\(['\"][abc]['\"],", line):
        return re.search(r"setreg\(['\"][abc]['\"],\s*['\"]([^'\"]*)['\"]", line)
def pytest_status(cleaned_line):
    return re.match(r'^(tests/.*?)(?=\s+(PASSED|FAILED|SKIPPED|XFAIL|ERROR|XPASS))', cleaned_line)
def test_release_workflow(job):
    assert not re.search("always|cancelled|failure", job.get("if", ""))
def result_files(fname):
    return re.match(r'scores_.*\.json', fname)
'''


def first_match(src):
    return [f for f in lint_source("g.py", src) if f.rule == "ETB-01-FIRST-MATCH"]


def test_first_match_keeps_every_confirmed_survey_shape():
    assert len(first_match(CONFIRMED_FIRST_MATCH)) == 18


def test_first_match_skips_answer_extraction_and_unrelated_regexes():
    assert first_match(NOISE_FIRST_MATCH) == []


def test_first_match_start_anchor_counts_only_without_multiline():
    bound = 'import re\ndef g(judgment):\n    return re.search(r"^GRADE: ([CPI])", judgment)\n'
    assert first_match(bound) == []
    assert len(first_match(bound.replace(', judgment)', ', judgment, re.M)'))) == 1
    assert len(first_match(bound.replace('r"^GRADE', 'r"(?m)^GRADE'))) == 1
    assert len(first_match(bound.replace('r"^GRADE', 'r"^.*?GRADE'))) == 1


def test_substring_order_reports_a_chain_once_at_its_head():
    hits = [f for f in lint_source("g.py", SUBSTRING) if f.rule == "ETB-01-SUBSTRING-ORDER"]
    assert [f.line for f in hits] == [3]


# ETB-03: the 37 survey hits were all config flags, file modes, fixtures and log strings.
DEFAULT_PASS_KEEP = r'''
import re
def run(resp):
    m = re.search(r"verdict: (pass|fail)", resp)
    verdict = m.group(1) if m else "pass"
    return verdict
def check(resp):
    m = re.search(r"correct: (yes|no)", resp)
    return {"correct": m.group(1) == "yes" if m else True}
def grade(resp):
    m = re.findall(r"\[\[([A-C])\]\]", resp)
    return Score(value=m[-1] if m else "A")
def judge(resp):
    m = re.search(r"PASS|FAIL", resp)
    return m.group(0) == "PASS" if m else True
'''
DEFAULT_PASS_MODULE = r'''
import re
class Extractor:
    def __call__(self, resp):
        m = re.search(r"\[\[([A-C])\]\]", resp)
        return m.group(1) if m else "A"
'''
DEFAULT_PASS_NOISE = r'''
import os
def cli(no_score, paused_now, temperature):
    score = False if no_score else True
    do_sample = False if temperature == 0 else True
    label = "yes (now)" if paused_now else "yes"
    return score, do_sample, label
def collect(output):
    write_mode = "w" if not os.path.exists(output) else "a"
    return open(output, write_mode)
def download(export, cond, agent):
    effective_export = export if export is not None else True
    is_available = cond.is_available(agent) if cond.available else True
    return effective_export, is_available
def _parse_args(args):
    return {k.split("=")[0]: k.split("=")[1] if "=" in k else True for k in args}
def grade_patch(vulnerability):
    status = "fail" if vulnerability.test_passes_if_vulnerable else "pass"
    return f"test should {status}"
class Model:
    def __init__(self, do_sample):
        self.do_sample: bool = do_sample if do_sample is not None else True
def test_limit(requests, limit, state, finalized, first, servers, run):
    assert len(requests) == limit if limit else True
    parked = "b" if state.sample_id == "a" else "a"
    run(pending=None if finalized else True)
    first_server = servers[first[1] if first else "a"]
    return parked, first_server
'''


def default_pass(src, name="utils.py"):
    return [f for f in lint_source(name, src) if f.rule == "ETB-03-DEFAULT-PASS"]


def test_default_pass_fires_in_grading_context_only():
    assert [f.line for f in default_pass(DEFAULT_PASS_KEEP)] == [5, 9, 12, 15]
    assert len(default_pass(DEFAULT_PASS_MODULE, "scorer.py")) == 1
    assert default_pass(DEFAULT_PASS_MODULE, "utils.py") == []
    assert default_pass(DEFAULT_PASS_NOISE, "eval.py") == []
    assert default_pass(DEFAULT_PASS_NOISE, "utils.py") == []


# ETB-11: per-path restore loops that swallow the failure (SWE-bench Pro v2 test.sh shape).
PER_PATH_RESTORE = """#!/bin/bash
set -uo pipefail
cd /app 2>/dev/null || cd /testbed
while IFS=' ' read -r kind path; do
    case "$kind" in
        T) git checkout HEAD -- "$path" 2>/dev/null || true ;;
        U) rm -f -- "$path" 2>/dev/null || true ;;
    esac
done < /tmp/reset_list.txt
while read -r p; do
  if git ls-files --error-unmatch -- "$p" >/dev/null 2>&1; then
    git checkout HEAD -- "$p" 2>/dev/null || true
  fi
done < /tmp/v5_paths.txt
set -e
git checkout HEAD -- tests/test_mod.py || :
"""
PER_PATH_SAFE = """#!/bin/bash
set -euo pipefail
cd /app
while read -r p; do
  git checkout HEAD -- "$p" || { echo "RESTORE_FAILED $p"; exit 1; }
done < /tmp/paths.txt
git checkout -b scratch || true
git checkout HEAD -- tests/a.py 2>/dev/null
"""


def test_per_path_restore_swallowed_failure_fires_even_under_set_e():
    hits = [f for f in lint_source("test.sh", PER_PATH_RESTORE) if f.rule == "ETB-11-RESTORE-FAILS-OPEN"]
    assert [f.line for f in hits] == [6, 12, 16]
    assert all("per-path" in f.message and "|| true" in f.message for f in hits)
    assert rules(PER_PATH_RESTORE, "test.sh") == ["ETB-11-RESTORE-FAILS-OPEN"]
    assert rules(PER_PATH_SAFE, "safe.sh") == []


def test_json_output_reports_files_scanned(tmp_path, capsys):
    from etbscan.__main__ import main
    (tmp_path / "g.py").write_text(FIRST_MATCH)
    (tmp_path / "ok.py").write_text(LAST_MATCH)
    (tmp_path / "notes.md").write_text("not linted")
    assert main(["lint", str(tmp_path), "--json"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["files_scanned"] == 2
    assert [f["rule"] for f in out["findings"]] == ["ETB-01-FIRST-MATCH", "ETB-01-FIRST-MATCH"]
    assert out["counts"] == {"high": 2}
    assert main(["lint", str(tmp_path)]) == 1
    assert "2 file(s) scanned" in capsys.readouterr().out
