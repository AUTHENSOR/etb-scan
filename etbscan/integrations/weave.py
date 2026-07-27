"""Scan a Weights & Biases Weave scorer for ETB-01 verdict-injection susceptibility.

A `weave.Scorer` reads the output of the system under evaluation and returns a
judgement. That is the trust boundary this tool measures.

    pip install "etb-scan[weave]"

    from etbscan.integrations.weave import scan_scorer
    result = scan_scorer(MyScorer(), trials=10)
    print(result.overall_asr, result.control_fp_rate, result.trustworthy)

Unlike a DeepEval metric, a Weave scorer **returns** its judgement rather than
writing it onto the instance, so no lock is needed and `max_workers` gives real
concurrency. Verified against weave 0.53.3, whose signature is
`Scorer.score(self, *, output, **kwargs)`.

Return shapes
-------------
Weave scorers return whatever is convenient: a bool, a float, or a dict such as
`{"correct": True}`. All three are passed through to etb-scan's verdict reader,
which handles booleans, enums, nested single-key dicts, and the numeric score
path. A shape it cannot read is reported **unscorable**, never as "did not
pass": coercing an uninterpretable judgement into a failing one is the fail-open
this tool exists to find.
"""

from __future__ import annotations

import inspect as _inspect
from typing import Any, Callable

__all__ = ["as_judge", "scan_scorer"]

_IMPORT_HINT = (
    "Weave is not installed. Install it with:\n"
    '    pip install "etb-scan[weave]"'
)

# Keys a Weave scorer commonly returns a pass/fail under. Checked in order.
_VERDICT_KEYS = ("passed", "correct", "pass", "verdict", "is_correct", "result")


def _require_weave() -> None:
    try:
        import weave  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised by hand
        raise ImportError(_IMPORT_HINT) from exc


def _normalize(raw: Any) -> dict:
    """Map a Weave scorer's return onto the verdict dict etb-scan reads."""
    if isinstance(raw, bool):
        return {"verdict": raw}
    if isinstance(raw, (int, float)):
        return {"score": raw}
    if isinstance(raw, dict):
        for key in _VERDICT_KEYS:
            if key in raw:
                return {"verdict": raw[key]}
        if "score" in raw:
            return {"score": raw["score"]}
        # A single-key dict of unknown name is unambiguous enough to read.
        if len(raw) == 1:
            return {"verdict": next(iter(raw.values()))}
        # Otherwise hand it over untouched and let the verdict reader decide;
        # it raises JudgeUnscorable rather than guessing, which is correct.
        return raw
    return {"verdict": raw}


def as_judge(scorer: Any, **score_kwargs: Any) -> Callable:
    """Adapt a `weave.Scorer` to the judge callable `scan` expects.

    Extra keyword arguments are forwarded to `score`, for scorers that take
    more than `output`. If the scorer accepts a parameter named `query`,
    `input`, or `question`, the scenario's question is passed through
    automatically.
    """
    _require_weave()

    score_fn = getattr(scorer, "score", None)
    if not callable(score_fn):
        raise TypeError(
            f"{type(scorer).__name__} has no callable .score(); "
            "is it a weave.Scorer?"
        )

    # weave.op wraps score, so read the signature off the underlying function
    # where one is exposed; otherwise fall back to the wrapper.
    target = getattr(score_fn, "resolve_fn", score_fn)
    try:
        params = set(_inspect.signature(target).parameters)
    except (TypeError, ValueError):  # pragma: no cover - exotic callables
        params = set()
    question_param = next(
        (p for p in ("query", "input", "question") if p in params), None
    )

    def judge(candidate: str, rubric: Any, question: str | None = None) -> dict:
        kwargs = dict(score_kwargs)
        if question_param and question is not None:
            kwargs.setdefault(question_param, question)
        try:
            raw = score_fn(output=candidate, **kwargs)
        except TypeError as exc:
            # A signature mismatch is a configuration error, not a verdict.
            return {"error": f"scorer signature mismatch: {exc}"}
        except Exception as exc:  # noqa: BLE001 - surfaced as unscorable
            return {"error": f"{type(exc).__name__}: {exc}"}

        if _inspect.isawaitable(raw):
            return {
                "error": (
                    "scorer returned an awaitable; etb-scan is synchronous. "
                    "Wrap the async scorer in a sync callable."
                )
            }
        if raw is None:
            return {"error": "scorer returned None"}
        return _normalize(raw)

    judge.__name__ = getattr(scorer, "name", None) or type(scorer).__name__
    return judge


def scan_scorer(scorer: Any, *, trials: int = 10, corpus=None, **kwargs):
    """Scan a Weave scorer. Returns a `ScanResult`.

    `trials` defaults to 10 because an LLM-backed scorer is stochastic and a
    single trial per scenario is too noisy to gate on. A scorer that is purely
    deterministic can use `trials=1`.
    """
    from etbscan import load_corpus, scan

    return scan(
        as_judge(scorer),
        corpus if corpus is not None else load_corpus(),
        trials=trials,
        **kwargs,
    )
