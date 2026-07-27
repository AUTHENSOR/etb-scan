"""An injectable judge must scan as injectable regardless of verdict SHAPE.

Regression for the critical defect: is_pass() read any unrecognised verdict as
FAIL, so a judge with identical decision logic to naive_judge (documented ASR
1.0) scanned as 0.0 with trustworthy=True, and both CI gates passed it green.
"""
import enum
import pytest
from etbscan import load_corpus, scan
from etbscan.judges import JudgeUnscorable, _honest_verdict, detect_verdict_injection, interpret_verdict

CORPUS = load_corpus()


class Verdict(enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"


def _injectable(shape):
    def judge(c, r, q=None):
        d = {"verdict": "PASS"} if detect_verdict_injection(c) else _honest_verdict(c, r)
        return shape(d)
    return judge


SHAPES = {
    "plain enum": lambda d: {**d, "verdict": Verdict[d["verdict"]]},
    "nested label dict": lambda d: {"verdict": {"label": d["verdict"]}},
    "passed boolean": lambda d: {"passed": d["verdict"] == "PASS"},
    "score only": lambda d: {"score": 10.0 if d["verdict"] == "PASS" else 2.0},
    "inspect C/I": lambda d: {"verdict": "C" if d["verdict"] == "PASS" else "I"},
    "lowercase": lambda d: {"verdict": d["verdict"].lower()},
    "yes/no": lambda d: {"verdict": "yes" if d["verdict"] == "PASS" else "no"},
}


@pytest.mark.parametrize("name,shape", list(SHAPES.items()))
def test_injectable_judge_detected_in_any_verdict_shape(name, shape):
    r = scan(_injectable(shape), CORPUS)
    assert r.overall_asr == 1.0, f"{name}: injectable judge scanned as {r.overall_asr}"
    assert r.n_errored == 0 and r.trustworthy


UNREADABLE = [
    {"verdict": "MAYBE"}, {"verdict": object()}, {}, {"grade": "A"},
    {"score": "high"}, {"verdict": None},
]


@pytest.mark.parametrize("v", UNREADABLE)
def test_uninterpretable_verdict_is_unscorable_not_fail(v):
    with pytest.raises(JudgeUnscorable):
        interpret_verdict(v, {})


def test_unreadable_judge_is_untrustworthy_not_clean():
    r = scan(lambda c, r_, q=None: {"verdict": "MAYBE"}, CORPUS)
    assert r.n_errored == len(CORPUS) and r.trustworthy is False


def test_documented_score_path_works():
    """README promises a numeric score is accepted. It must actually be."""
    assert interpret_verdict({"score": 10.0}, {}) is True
    assert interpret_verdict({"score": 1.0}, {}) is False


def test_pytest_fixture_refuses_an_unscorable_judge(etb_scan):
    with pytest.raises(pytest.fail.Exception):
        etb_scan(lambda c, r, q=None: {"verdict": "MAYBE"})
