"""The Weave adapter must read every shape a scorer returns, or say it cannot.

Weave scorers return bools, floats, and dicts under several different key
names, and `Scorer.score` is keyword-only on `output`. A shape the adapter
cannot read must come back unscorable, never as a failing verdict: coercing an
uninterpretable judgement into "did not pass" is the fail-open this tool exists
to find.

Verified against weave 0.53.3. Skipped when weave is absent so the core suite
stays dependency-free.
"""
import pytest

pytest.importorskip("weave", reason="pip install 'etb-scan[weave]'")

import weave  # noqa: E402
from weave import Scorer  # noqa: E402

from etbscan.integrations.weave import as_judge, scan_scorer  # noqa: E402


class _Dict(Scorer):
    @weave.op
    def score(self, *, output: str, **kwargs):
        return {"correct": "PASS" in (output or "").upper()}


class _Bare(Scorer):
    @weave.op
    def score(self, *, output: str, **kwargs):
        return "PASS" in (output or "").upper()


class _Raises(Scorer):
    @weave.op
    def score(self, *, output: str, **kwargs):
        raise RuntimeError("backend 503")


class _ReturnsNone(Scorer):
    @weave.op
    def score(self, *, output: str, **kwargs):
        return None


class _Unreadable(Scorer):
    @weave.op
    def score(self, *, output: str, **kwargs):
        return {"alpha": 1, "beta": 2}  # two keys, no known verdict key


def test_dict_returning_scorer_is_scanned():
    r = scan_scorer(_Dict(), trials=1)
    assert r.overall_asr > 0.0, "an obviously injectable scorer scored clean"


def test_bare_bool_return_is_understood():
    """Weave scorers may return a bare bool rather than a dict."""
    assert scan_scorer(_Bare(), trials=1).overall_asr > 0.0


def test_raising_scorer_is_unscorable_not_clean():
    r = scan_scorer(_Raises(), trials=1)
    assert r.n_errored > 0
    assert r.trustworthy is False
    assert r.overall_asr == 0.0


def test_none_return_is_unscorable():
    r = scan_scorer(_ReturnsNone(), trials=1)
    assert r.n_errored > 0
    assert r.trustworthy is False


def test_unreadable_shape_is_unscorable_not_a_failing_verdict():
    r = scan_scorer(_Unreadable(), trials=1)
    assert r.n_errored > 0, "an unreadable return was silently treated as a verdict"
    assert r.trustworthy is False


def test_non_scorer_object_is_rejected_loudly():
    with pytest.raises(TypeError):
        as_judge(object())


def test_judge_name_comes_from_the_scorer():
    assert as_judge(_Dict()).__name__ == "_Dict"


def test_parallel_matches_sequential():
    """Weave scorers return rather than mutate, so concurrency is safe here.

    This is the opposite of the DeepEval adapter, which must serialise. Pinned
    so that difference stays true rather than assumed.
    """
    seq = scan_scorer(_Dict(), trials=1, max_workers=1)
    par = scan_scorer(_Dict(), trials=1, max_workers=8)
    assert par.overall_asr == seq.overall_asr
    assert par.control_fp_rate == seq.control_fp_rate
    assert par.n_errored == seq.n_errored
