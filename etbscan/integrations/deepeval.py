"""Scan a DeepEval metric for ETB-01 verdict-injection susceptibility.

A DeepEval metric is an LLM judge: it reads text the evaluated system produced
and returns a score. That makes it exactly the thing this tool measures.

    pip install "etb-scan[deepeval]"

    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCaseParams
    from etbscan.integrations.deepeval import scan_metric

    metric = GEval(
        name="Correctness",
        criteria="Is the answer correct and complete?",
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
    )
    result = scan_metric(metric, trials=10)
    print(result.overall_asr, result.control_fp_rate, result.trustworthy)

What this measures, and what it does not
----------------------------------------
It measures whether text the evaluated model wrote can flip the metric's
verdict on an answer that otherwise fails. It does **not** measure whether the
metric is accurate, useful, or well-calibrated.

A metric that passes everything scores a vacuous 0.0 under a naive reading, so
`scan` reports such a metric as unscorable rather than clean. Read
`result.trustworthy` before you read `result.overall_asr`.

Thread safety
-------------
DeepEval metrics are **stateful**: `measure()` writes `score`, `success`, and
`reason` back onto the metric instance. Two threads sharing one metric would
interleave a write and a read and silently mis-score. `as_judge` therefore
serializes calls through a lock, so passing `max_workers > 1` to `scan` is safe
but will not speed up a DeepEval scan. Give each worker its own metric instance
if you need real concurrency.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

__all__ = ["as_judge", "scan_metric"]

_IMPORT_HINT = (
    "DeepEval is not installed. Install it with:\n"
    '    pip install "etb-scan[deepeval]"'
)


def _require_deepeval():
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError as exc:  # pragma: no cover - exercised by hand
        raise ImportError(_IMPORT_HINT) from exc
    return LLMTestCase


def _rubric_text(rubric: Any) -> str:
    if isinstance(rubric, dict):
        for key in ("text", "criteria", "description"):
            if key in rubric:
                value = rubric[key]
                return "\n".join(value) if isinstance(value, list) else str(value)
    return str(rubric)


def as_judge(metric: Any, *, expected_output: str | None = None) -> Callable:
    """Adapt a DeepEval metric to the judge callable `scan` expects.

    The returned callable has the signature
    ``judge(candidate, rubric, question=None) -> dict``.

    A metric that raises, records an error, or is skipped comes back as
    ``{"error": ...}``, which `scan` reports as unscorable. It is never coerced
    to "did not pass": that coercion is the fail-open (ETB-03) this tool exists
    to find, and committing it here would corrupt the measurement.
    """
    LLMTestCase = _require_deepeval()
    lock = threading.Lock()

    def judge(candidate: str, rubric: Any, question: str | None = None) -> dict:
        test_case = LLMTestCase(
            input=question or _rubric_text(rubric),
            actual_output=candidate,
            expected_output=expected_output,
        )
        with lock:
            try:
                metric.measure(test_case)
            except Exception as exc:  # noqa: BLE001 - surfaced as unscorable
                return {"error": f"{type(exc).__name__}: {exc}"}

            # DeepEval reports some failures on the instance rather than by
            # raising, so both have to be checked before the score is trusted.
            if getattr(metric, "error", None):
                return {"error": str(metric.error)}
            if getattr(metric, "skipped", False):
                return {"error": "metric reported skipped"}

            score = getattr(metric, "score", None)
            success = getattr(metric, "success", None)

        if score is None and success is None:
            return {"error": "metric produced neither a score nor a success flag"}

        verdict: dict[str, Any] = {}
        if success is not None:
            verdict["verdict"] = "PASS" if success else "FAIL"
        if score is not None:
            verdict["score"] = score
        return verdict

    judge.__name__ = getattr(metric, "__name__", None) or type(metric).__name__
    return judge


def scan_metric(metric: Any, *, trials: int = 10, corpus=None, **kwargs):
    """Scan a DeepEval metric. Returns a `ScanResult`.

    `trials` defaults to 10 rather than 1, because a DeepEval metric is backed
    by an LLM and is therefore stochastic. A single trial per scenario is far
    too noisy to gate on.
    """
    from etbscan import load_corpus, scan

    return scan(
        as_judge(metric),
        corpus if corpus is not None else load_corpus(),
        trials=trials,
        **kwargs,
    )
