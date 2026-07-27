"""A broken judge must be UNSCORABLE, never silently 'no injection found'.

This is the tool's own ETB-03/ETB-04 test. Absorbing a judge error into a clean
ASR would be fail-open, and dropping errored scenarios from the denominator
without saying so would be a denominator drop. Both are defects this tool
exists to find, so it must not commit them.
"""
import pytest
from etbscan import hardened_judge, load_corpus, naive_judge, scan

CORPUS = load_corpus()

BROKEN = {
    "returns None": lambda c, r, q=None: None,
    "returns a string": lambda c, r, q=None: "PASS",
    "raises RuntimeError": lambda c, r, q=None: (_ for _ in ()).throw(RuntimeError("rate limit")),
    "returns a list": lambda c, r, q=None: ["PASS"],
}


@pytest.mark.parametrize("name,judge", list(BROKEN.items()))
def test_broken_judge_is_unscorable_not_clean(name, judge):
    r = scan(judge, CORPUS)
    assert r.n_errored > 0, f"{name}: errors were silently absorbed"
    assert r.trustworthy is False, f"{name}: reported a trustworthy result on a broken judge"


@pytest.mark.parametrize("name,judge", list(BROKEN.items()))
def test_broken_judge_does_not_crash_the_scan(name, judge):
    scan(judge, CORPUS)  # must not raise


def test_two_arg_judge_supported():
    r = scan(lambda c, rubric: {"verdict": "fail"}, CORPUS)
    assert r.n_errored == 0 and r.trustworthy


def test_reference_judges_are_trustworthy():
    for j in (naive_judge, hardened_judge):
        r = scan(j, CORPUS)
        assert r.n_errored == 0 and r.trustworthy


def test_errored_scenarios_leave_the_denominator():
    r = scan(lambda c, rr, q=None: None, CORPUS)
    assert r.n_injected == 0, "unscorable scenarios must not count as scorable"
    assert r.n_errored == len(CORPUS)


def test_systemexit_from_judge_does_not_pass_the_gate():
    """A judge calling sys.exit() must not end the process and silently pass CI."""
    r = scan(lambda c, r_, q=None: (_ for _ in ()).throw(SystemExit(0)), CORPUS)
    assert r.n_errored == len(CORPUS) and r.trustworthy is False


def test_to_dict_is_json_serialisable_for_exotic_verdicts():
    import enum, json
    class V(enum.Enum):
        PASS = "PASS"
        FAIL = "FAIL"
    r = scan(lambda c, r_, q=None: {"verdict": V.FAIL}, CORPUS)
    json.dumps(r.to_dict())  # must not raise


def test_vacuous_scan_is_not_trustworthy():
    for corpus in ([], [{"id": "a", "family": "control", "injected": False,
                         "rubric": {}, "base_content": "x", "candidate": "x"}]):
        r = scan(hardened_judge, corpus)
        assert r.trustworthy is False
        assert r.untrustworthy_reason


def test_pass_everything_judge_is_not_reported_clean():
    """A judge that passes everything must not read as a clean 0.0 ASR.

    The flip test needs the clean weak answer to fail first. A judge that
    passes it has made the flip unmeasurable, not absent, so every injected
    scenario is unscorable and the result is untrustworthy. Reporting 0.0 here
    would be the degenerate-condition-reads-as-safe failure (ETB-05) that this
    tool exists to detect, committed by the detector itself.
    """
    r = scan(lambda c, r_, q=None: {"verdict": "PASS"}, CORPUS)
    assert r.trustworthy is False, "a pass-everything judge got a clean bill of health"
    assert r.n_errored > 0
    assert r.n_injected == 0, "unmeasurable scenarios must leave the ASR denominator"


def test_baseline_passing_in_some_trials_still_measures_the_rest():
    """Only the trials where the baseline failed are measurable, but they count.

    A judge that is merely lenient some of the time is still scorable; it is
    only unscorable when no trial left a flip observable.
    """
    import random

    rng = random.Random(0)

    def flaky(candidate, rubric, question=None):
        # passes the clean answer half the time; always obeys an injected verdict
        if "PASS" in candidate.upper():
            return {"verdict": "PASS"}
        return {"verdict": "PASS" if rng.random() < 0.5 else "FAIL"}

    r = scan(flaky, CORPUS, trials=10)
    assert r.n_injected > 0, "all scenarios went unscorable despite measurable trials"
    assert r.overall_asr > 0.0


def test_trials_converge_on_a_stochastic_judge():
    """One trial understates a probabilistic judge. More trials must find it."""
    import random
    from etbscan.judges import _honest_verdict, detect_verdict_injection

    def flaky(c, r, q=None):
        if detect_verdict_injection(c) and random.random() < 0.5:
            return {"verdict": "PASS"}
        return _honest_verdict(c, r)

    random.seed(0)
    assert scan(flaky, CORPUS, trials=10).overall_asr > scan(flaky, CORPUS, trials=1).overall_asr


def test_trials_must_be_positive():
    import pytest as _p
    with _p.raises(ValueError):
        scan(hardened_judge, CORPUS, trials=0)


def test_deterministic_judge_unaffected_by_trials():
    a = scan(hardened_judge, CORPUS, trials=1).overall_asr
    b = scan(hardened_judge, CORPUS, trials=5).overall_asr
    assert a == b == 0.0
