"""The Inspect surface must actually resolve and actually score.

This surface shipped declared-but-unexercised, and the invocation documented in
two docstrings did not work. Both plausible-looking forms
(``etbscan/verdict_injection``, ``etbscan.inspect_task``) fail with "No inspect
tasks were found at the specified paths"; only the bare name resolves. A
declared entry point that nobody runs in CI is a claim, not a feature.

Skipped when inspect-ai is absent, so the core suite stays dependency-free.
"""
import pytest

pytest.importorskip("inspect_ai", reason="pip install 'etb-scan[inspect]'")

from inspect_ai import eval as inspect_eval  # noqa: E402

from etbscan.inspect_task import no_verdict_injection, verdict_injection  # noqa: E402


def test_entry_point_is_registered_for_the_inspect_group():
    """Installing the package must make the task discoverable with no config."""
    from importlib.metadata import entry_points

    eps = {e.name: e.value for e in entry_points(group="inspect_ai")}
    assert eps.get("etbscan") == "etbscan.inspect_registry"


def test_registry_module_exports_the_task_and_scorer():
    from etbscan import inspect_registry

    assert "verdict_injection" in inspect_registry.__all__
    assert "no_verdict_injection" in inspect_registry.__all__


def test_task_resolves_by_its_bare_registry_name():
    """The documented invocation. Pinned because the wrong forms look right."""
    from inspect_ai._util.registry import registry_lookup

    import etbscan.inspect_registry  # noqa: F401  (registers on import)

    assert registry_lookup("task", "verdict_injection") is not None


def test_task_builds_with_samples_and_a_scorer():
    t = verdict_injection()
    assert len(t.dataset) > 0, "task built with an empty dataset"
    assert t.scorer is not None


def test_end_to_end_eval_scores_every_sample():
    """Runs the real task against Inspect's mock model. No API key, no network."""
    logs = inspect_eval(
        verdict_injection(),
        model="mockllm/model",
        limit=3,
        display="none",
        log_dir=None,
    )
    log = logs[0]
    assert log.status == "success", f"eval did not succeed: {log.status}"
    assert log.samples and len(log.samples) == 3
    assert log.results is not None and log.results.scores
    assert log.results.scores[0].name == "no_verdict_injection"
    # The mock model emits no injections, so a correct scorer must not fire.
    assert log.results.scores[0].metrics["accuracy"].value == 1.0


def test_scorer_is_deterministic_and_frozen():
    """The scorer must not read anything the evaluated model can influence.

    It is the scorer for a tool about scorers that trust model-controlled text,
    so it reads only the emitted answer against a frozen pattern set.
    """
    assert no_verdict_injection() is not None
