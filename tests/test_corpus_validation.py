"""A malformed corpus must fail before any judge call, not halfway through.

A missing key used to either raise a bare KeyError after the judge had already
run on earlier rows, or silently substitute an empty string, which deflates the
ASR with no signal at all.
"""
import pytest
from etbscan import scan

JUDGE = lambda c, r, q=None: {"verdict": "fail"}
ROW = lambda **kw: {**{"id": "a", "family": "direct_verdict_override", "injected": True,
                       "rubric": {}, "base_content": "x", "candidate": "y"}, **kw}


@pytest.mark.parametrize("key", ["id", "family", "injected", "candidate", "base_content"])
def test_missing_required_key_is_rejected(key):
    with pytest.raises(ValueError, match="missing required"):
        scan(JUDGE, [{k: v for k, v in ROW().items() if k != key}])


def test_duplicate_scenario_ids_rejected():
    with pytest.raises(ValueError, match="duplicate scenario id"):
        scan(JUDGE, [ROW(), ROW()])


def test_non_dict_row_rejected():
    with pytest.raises(ValueError, match="expected a dict"):
        scan(JUDGE, ["nope"])


def test_validation_runs_before_any_judge_call():
    calls = []
    def counting(c, r, q=None):
        calls.append(1)
        return {"verdict": "fail"}
    with pytest.raises(ValueError):
        scan(counting, [ROW(), {k: v for k, v in ROW(id="b").items() if k != "candidate"}])
    assert not calls, "judge was called before the corpus was validated"


def test_custom_family_appears_in_per_family():
    r = scan(JUDGE, [ROW(family="my_custom_family")])
    assert "my_custom_family" in r.per_family


def test_rubric_is_isolated_between_arms():
    seen = []
    def spy(c, rubric, q=None):
        seen.append(id(rubric))
        rubric["mutated"] = True
        return {"verdict": "fail"}
    scan(spy, [ROW(rubric={"k": 1})])
    assert seen[0] != seen[1], "both arms received the same mutable rubric"
