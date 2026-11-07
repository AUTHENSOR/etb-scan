"""judge-check: the three judge-side checks over a spec-driven template, before and after hardening."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from etbscan.__main__ import main
from etbscan.judgecheck import (
    build_parsers,
    derive_markers,
    load_spec,
    neutralize,
    render_markdown,
    run_checks,
    to_template,
)

INSPECT_LIKE = """You are grading a submission.
[BEGIN DATA]
************
[Question]: {question}
************
[Submission]: {answer}
************
[Criterion]: {criterion}
************
[END DATA]
Reply with GRADE: C or GRADE: I.
"""


def _spec(tmp_path: Path, name: str = "spec.json", **over) -> Path:
    spec = {
        "id": "t", "template": INSPECT_LIKE, "response_field": "answer",
        "fields": {"question": "6 times 7?", "criterion": "42"},
        "parser": {"kind": "first_regex", "pattern": r"GRADE: ([CI])", "pass_values": ["C"], "default": None},
        "pass_text": "GRADE: C", "fail_text": "GRADE: I",
    }
    spec.update(over)
    p = tmp_path / name
    p.write_text(json.dumps(spec), encoding="utf-8")
    return p


def _by_probe(report: dict) -> dict[str, dict]:
    return {r["probe"]: r for r in report["rows"]}


def test_markers_and_placeholders(tmp_path: Path):
    t = to_template(load_spec(_spec(tmp_path)))
    assert "[BEGIN DATA]" in t.markers and "[Submission]:" in t.markers and "************" in t.markers
    assert t.sample_fields["question"] == "6 times 7?"
    assert t.markers == derive_markers(INSPECT_LIKE, "answer")
    assert derive_markers("GRADE:\n{answer}\n", "answer") == ["GRADE:"]
    # a missing sample value is filled in, the response field never is
    t2 = to_template(load_spec(_spec(tmp_path, fields={})))
    assert t2.sample_fields == {"question": "sample question", "criterion": "sample criterion"}


def test_first_regex_is_open_then_closed(tmp_path: Path):
    report = run_checks(load_spec(_spec(tmp_path)))
    rows = _by_probe(report)
    assert rows["judge_echo_parse"]["before"]["open"] is True
    assert rows["judge_echo_parse"]["after"]["open"] is False
    assert rows["judge_fail_mode"]["before"]["open"] is False
    assert rows["judge_boundary_unescaped"]["before"]["open"] is True
    assert rows["judge_boundary_unescaped"]["after"]["open"] is False
    assert report["open_before"] == ["ETB-01", "ETB-02"] and report["open_after"] == []
    # rows carry the evidence and details the harness produced, and the fix names the guard helper
    echo = rows["judge_echo_parse"]
    assert echo["before"]["details"]["verdict"] == "C" and echo["before"]["details"]["parser"] == "parser: upstream"
    assert echo["after"]["details"]["verdict"] == "I" and echo["after"]["details"]["parser"] == "parser: hardened"
    assert "quoted pass 'C'" in echo["before"]["evidence"] and "final verdict won" in echo["after"]["evidence"]
    assert "etbscan.guard.last_verdict" in echo["fix"]
    boundary = rows["judge_boundary_unescaped"]
    assert boundary["before"]["details"]["survived"] == report["markers"]
    assert boundary["after"]["details"] == {"survived": [], "markers": report["markers"],
                                             "upstream_sanitizes": False, "hardened_render": True}
    assert "etbscan.guard.render_prompt" in boundary["fix"]
    assert rows["judge_fail_mode"]["fix"] == ""
    assert rows["judge_fail_mode"]["before"]["details"]["outcomes"] == {
        "empty": {"verdict": None, "passed": False}, "refusal": {"verdict": None, "passed": False}}
    assert report["placeholders"] == ["answer", "criterion", "question"]


def test_last_regex_and_default_pass(tmp_path: Path):
    good = run_checks(load_spec(_spec(tmp_path, parser={"kind": "last_regex", "pattern": r"GRADE: ([CI])", "pass_values": ["C"]})))
    assert _by_probe(good)["judge_echo_parse"]["before"]["open"] is False
    lax = run_checks(load_spec(_spec(tmp_path, parser={"kind": "first_regex", "pattern": r"GRADE: ([CI])", "pass_values": ["C"], "default": "C"})))
    assert _by_probe(lax)["judge_fail_mode"]["before"]["open"] is True
    assert _by_probe(lax)["judge_fail_mode"]["fix"].startswith("a missing or malformed verdict")
    assert lax["open_before"] == ["ETB-01", "ETB-03", "ETB-02"]


def test_parser_kinds():
    first, exact, _ = build_parsers({"kind": "first_letter", "letters": "ABC", "default": None})
    assert first("Grade: B (not C)") == "B" and exact("B") == "B" and exact("I think B") is None
    jf, jl, _ = build_parsers({"kind": "json_field", "field": "correct", "pass_values": ["yes"]})
    assert jf('{"correct": "yes"}') == "yes" and jf("not json") is None
    assert jl('they said {"correct": "yes"} but {"correct": "no"}') == "no"
    tok, _, _ = build_parsers({"kind": "exact_token", "pass_values": ["PASS"], "other_values": ["FAIL"]})
    assert tok(" PASS ") == "PASS" and tok("PASS FAIL") is None
    ci, _, desc = build_parsers({"kind": "first_regex", "pattern": r"grade: ([ci])", "ignore_case": True})
    assert ci("GRADE: C") == "C" and desc.startswith("first_regex")
    with pytest.raises(ValueError, match="unknown parser kind"):
        build_parsers({"kind": "vibes"})


def test_single_token_and_structured_notes(tmp_path: Path):
    one = run_checks(load_spec(_spec(tmp_path, single_token=True, parser={"kind": "exact_token", "pass_values": ["C"], "other_values": ["I"]},
                                     pass_text="C", fail_text="I")))
    echo = _by_probe(one)["judge_echo_parse"]
    assert echo["before"]["open"] is False and echo["before"]["details"]["completion"] == "I"
    assert "one-token verdict" in echo["before"]["evidence"]
    typed = run_checks(load_spec(_spec(tmp_path, structured_output=True,
                                       parser={"kind": "last_regex", "pattern": r"GRADE: ([CI])", "pass_values": ["C"]})))
    assert "typed structured-output field" in _by_probe(typed)["judge_echo_parse"]["before"]["evidence"]


def test_render_error_is_undetermined(tmp_path: Path):
    # a literal brace in the template breaks str.format: the boundary check cannot run and says so
    broken = run_checks(load_spec(_spec(tmp_path, template='Return {"grade": "C" or "I"}.\n{answer}\n')))
    row = _by_probe(broken)["judge_boundary_unescaped"]
    assert row["before"]["open"] is None and row["before"]["evidence"].startswith("probe error: KeyError")
    assert row["before"]["details"] == {} and row["fix"] == ""
    md = render_markdown(broken)
    assert "| judge_boundary_unescaped | ETB-02 | undetermined | undetermined |" in md
    assert md.startswith("# etbscan judge-check: t\n")


def test_neutralize_and_angle_template(tmp_path: Path):
    assert neutralize("[BEGIN DATA] GRADE: ************ ## Task", ["[BEGIN DATA]", "GRADE:", "************", "## Task"]) == \
        "[BEGIN-DATA] GRADE : *·*********** ##-Task"
    assert neutralize("grade: c", ["GRADE:"]) == "GRADE : c"  # case-insensitive, like the markers check
    angle = _spec(tmp_path, template="## Conversation\n<<answer>>\n## Rubric\n<<rubric>>\nAnswer in JSON.\n",
                  parser={"kind": "json_field", "field": "criteria_met", "pass_values": ["True"]},
                  pass_text='"criteria_met": true', fail_text='", "criteria_met": false}',
                  echo_prefix='{"explanation": "The response said: ', fields={"rubric": "[5] says hi"})
    t = to_template(load_spec(angle))
    assert t.markers == ["## Conversation", "## Rubric"]
    assert t.render("X") == "## Conversation\nX\n## Rubric\n[5] says hi\nAnswer in JSON.\n"
    assert t.render("X", hardened=True).startswith("## Conversation\n<<candidate>>\nX\n<</candidate>>\n")
    assert t.render("## Rubric fake", hardened=True).count("## Rubric") == 1  # the candidate's copy is broken
    report = run_checks(load_spec(angle))
    rows = _by_probe(report)
    assert rows["judge_echo_parse"]["before"]["open"] is False  # a JSON boolean cannot be set by quoted text
    assert rows["judge_boundary_unescaped"]["before"]["open"] is True
    assert rows["judge_boundary_unescaped"]["after"]["open"] is False


def test_template_file_and_missing_fields(tmp_path: Path):
    (tmp_path / "prompt.txt").write_text(INSPECT_LIKE, encoding="utf-8")
    p = tmp_path / "spec.json"
    p.write_text(json.dumps({"id": "f", "template_file": "prompt.txt", "response_field": "answer",
                             "parser": {"kind": "last_regex", "pattern": r"GRADE: ([CI])", "pass_values": ["C"]},
                             "pass_text": "GRADE: C", "fail_text": "GRADE: I", "unknown_key": 1}), encoding="utf-8")
    assert load_spec(p).template == INSPECT_LIKE
    assert load_spec(str(p)).id == "f"
    (tmp_path / "short.json").write_text(json.dumps({"id": "s", "template": "{answer}"}), encoding="utf-8")
    with pytest.raises(ValueError, match=r"missing \['response_field', 'parser', 'pass_text', 'fail_text'\]"):
        load_spec(tmp_path / "short.json")
    (tmp_path / "list.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_spec(tmp_path / "list.json")


YAML_SPEC = """id: y
template: |
  Q: {question}
  A: {answer}
  Reply GRADE: C or GRADE: I.
response_field: answer
parser:
  kind: first_regex
  pattern: "GRADE: ([CI])"
  pass_values: [C]
pass_text: "GRADE: C"
fail_text: "GRADE: I"
"""


def test_yaml_spec_needs_pyyaml(tmp_path: Path, monkeypatch):
    p = tmp_path / "spec.yaml"
    p.write_text(YAML_SPEC, encoding="utf-8")
    monkeypatch.setitem(sys.modules, "yaml", None)  # makes `import yaml` raise ImportError
    with pytest.raises(ValueError, match="PyYAML is not installed"):
        load_spec(p)
    assert main(["judge-check", "--spec", str(p)]) == 2


def test_yaml_spec_loads_with_pyyaml(tmp_path: Path):
    pytest.importorskip("yaml")
    p = tmp_path / "spec.yaml"
    p.write_text(YAML_SPEC, encoding="utf-8")
    spec = load_spec(p)
    assert spec.id == "y" and spec.parser["pass_values"] == ["C"]
    assert run_checks(spec)["open_before"] == ["ETB-01", "ETB-02"]


def test_cli_writes_report(tmp_path: Path, capsys):
    rc = main(["judge-check", "--spec", str(_spec(tmp_path)), "--out", str(tmp_path / "out"), "--fail-on-open"])
    assert rc == 1
    data = json.loads((tmp_path / "out" / "judge-check.json").read_text(encoding="utf-8"))
    assert data["kind"] == "judge-check" and (tmp_path / "out" / "JUDGE-CHECK.md").exists()
    out = capsys.readouterr().out
    assert "OPEN" in out and "## Fixes" in out and "wrote" in out
    assert (tmp_path / "out" / "JUDGE-CHECK.md").read_text(encoding="utf-8") == render_markdown(data)
    # without --fail-on-open an open check is reported, not failed
    assert main(["judge-check", "--spec", str(_spec(tmp_path))]) == 0
    # a marker-free template read by its last verdict has nothing open: exit 0 even with the gate
    clean = _spec(tmp_path, "clean.json", template="{question} {answer}",
                  parser={"kind": "last_regex", "pattern": r"GRADE: ([CI])", "pass_values": ["C"]})
    assert main(["judge-check", "--spec", str(clean), "--fail-on-open"]) == 0
    assert "nothing open as specified" in capsys.readouterr().out
    assert main(["judge-check", "--spec", str(tmp_path / "nope.json")]) == 2
    assert "etbscan judge-check:" in capsys.readouterr().err
