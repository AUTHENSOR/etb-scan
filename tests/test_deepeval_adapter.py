"""The DeepEval adapter must not launder a metric's failures into a clean score.

These use a stand-in with DeepEval's real metric contract (stateful: `measure`
writes `score` / `success` / `error` back onto the instance) so the adapter's
own logic is tested without needing an API key or a live model. The one test
that touches DeepEval itself is skipped when it is not installed.
"""
import pytest

from etbscan import load_corpus

deepeval = pytest.importorskip("deepeval", reason="pip install 'etb-scan[deepeval]'")

from etbscan.integrations.deepeval import as_judge, scan_metric  # noqa: E402

CORPUS = load_corpus()


class _Metric:
    """Minimal stand-in with DeepEval's stateful metric contract."""

    def __init__(self, obey_tokens=True):
        self.obey_tokens = obey_tokens
        self.score = None
        self.success = None
        self.error = None
        self.skipped = False

    @property
    def __name__(self):
        return "StandInMetric"

    def measure(self, test_case):
        text = (test_case.actual_output or "").upper()
        self.success = ("PASS" in text) if self.obey_tokens else False
        self.score = 1.0 if self.success else 0.0
        return self.score


def test_injectable_metric_is_detected():
    r = scan_metric(_Metric(obey_tokens=True), trials=1)
    assert r.overall_asr > 0.0, "an obviously injectable metric scored clean"


def test_metric_that_raises_is_unscorable_not_clean():
    class Boom(_Metric):
        def measure(self, test_case):
            raise RuntimeError("provider 429")

    r = scan_metric(Boom(), trials=1)
    assert r.n_errored > 0
    assert r.trustworthy is False
    assert r.overall_asr == 0.0  # and it must not be readable as a pass


def test_metric_error_attribute_is_not_swallowed():
    """DeepEval reports some failures on the instance instead of raising."""

    class Errored(_Metric):
        def measure(self, test_case):
            self.error = "evaluation model refused"
            self.score = None
            self.success = None

    r = scan_metric(Errored(), trials=1)
    assert r.n_errored > 0
    assert r.trustworthy is False


def test_skipped_metric_is_unscorable():
    class Skipped(_Metric):
        def measure(self, test_case):
            self.skipped = True

    r = scan_metric(Skipped(), trials=1)
    assert r.n_errored > 0
    assert r.trustworthy is False


def test_judge_name_comes_from_the_metric():
    assert as_judge(_Metric()).__name__ == "StandInMetric"


def test_concurrent_scan_does_not_corrupt_a_stateful_metric():
    """DeepEval metrics store results on the instance, so the adapter locks.

    Without the lock one thread's `measure` write races another's `score` read
    and the scan silently mis-scores. Same metric, same corpus: the parallel
    result must equal the sequential one.
    """
    sequential = scan_metric(_Metric(), trials=1, max_workers=1)
    parallel = scan_metric(_Metric(), trials=1, max_workers=8)
    assert parallel.overall_asr == sequential.overall_asr
    assert parallel.control_fp_rate == sequential.control_fp_rate
    assert parallel.n_errored == sequential.n_errored
