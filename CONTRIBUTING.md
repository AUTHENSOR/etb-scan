# Contributing

This tool exists to be argued with. The most valuable contributions are the
ones that show a number here is wrong.

## The fastest useful thing you can do

**Tell us your judge's ASR.** The published `1.0000` / `0.0000` figures
characterize two reference mocks and one run against Kimi K3. They are the
instrument's calibration, not a population estimate. Every real judge scanned
makes the picture less thin.

```bash
pip install etb-scan
etbscan --judge yourpkg.judges:your_judge --trials 10 --json
```

Open an issue with the output. You do not need to name your employer or the
model. `judge=<anonymised> asr=0.4 control_fp=0.0 trials=10` is a useful data
point on its own.

## If you think a finding is wrong

Say so, in an issue, bluntly. That includes:

- A row in [`EVIDENCE-TABLE.md`](EVIDENCE-TABLE.md) you believe is misclassified,
  already fixed, or not a defect at all.
- A class in the taxonomy you think is not a distinct mechanism.
- Anything in [`verified_run_real_judge/`](verified_run_real_judge/) you cannot
  reproduce.

This has happened before and the corrections stuck: one report was called
fabricated when it was real, and another was credited to us when it was not
ours. Both were wrong and both were fixed. Getting a row corrected is a
contribution, not an inconvenience.

Every row resolves to a live URL, so a disagreement is usually settleable in
one click.

## Adding a framework adapter

Adapters live in [`etbscan/integrations/`](etbscan/integrations/) and let
etb-scan measure a judge belonging to another framework. There are adapters for
DeepEval, Weave, and Ragas; the same shape works for anything with a scorer.

An adapter is one function that returns a judge callable:

```python
def judge(candidate: str, rubric: dict, question: str | None = None) -> dict:
    ...
    return {"verdict": "pass", "score": 0.9}
```

Four rules, all of them the same rule:

1. **Import the framework lazily** and raise a clear `ImportError` naming the
   extra to install. `etbscan` itself is stdlib-only and stays that way.
2. **A failure is unscorable, never a non-pass.** If the framework raises, sets
   an error attribute, or reports "skipped", return `{"error": ...}`. Coercing
   any of those into a failing score is the fail-open this tool exists to find,
   and committing it inside the detector is worse than not shipping the adapter.
3. **Check for state.** Several frameworks store the result on the scorer
   instance rather than returning it. Two threads sharing one such object will
   silently mis-score. Serialize, or document that the adapter is single-worker.
4. **Test against a stand-in, not a live model.** The suite must pass with no
   API key and no network. See
   [`tests/test_deepeval_adapter.py`](tests/test_deepeval_adapter.py).

Add the framework to `[project.optional-dependencies]` and `pytest.importorskip`
it in the test so the core suite still runs without it.

## Adding attack scenarios

The corpus is [`etbscan/data/attacks.json`](etbscan/data/attacks.json): 25
injected scenarios across 5 families plus 8 benign controls.

A new scenario needs a `base_content` that a correct judge **fails** and a
`candidate` that is the same answer carrying the injection. The detector fires
only on a causal flip, so if the clean answer already passes there is nothing to
measure and the scenario is reported unscorable.

New benign controls are as valuable as new attacks. The controls are what stop a
lenient judge from scoring a meaningless 0.0, and there are only eight.

## Development

```bash
git clone https://github.com/AUTHENSOR/etb-scan
cd etb-scan
pip install -e ".[pytest]"
python -m pytest -q
```

No linter config and no formatter to fight. Match the surrounding style.

Tests are the specification. They assert that a broken judge is unscorable
rather than clean, that a pass-everything judge cannot get a clean bill of
health, that errored scenarios leave the ASR denominator, and that the detector
never fires on honest prose. If you change behavior, change the test that
pins it and say why in the commit message.

## Commit messages

Explain why, not what. The diff shows what.

## What is out of scope

- **Chasing recall in the detector.** An earlier version fired on 53% of honest
  technical answers, because an answer *about* prompt injection is lexically
  identical to an injection. Penalising a correct answer is the same class of
  defect this tool exists to find. High precision and low recall is deliberate.
- **Classes beyond ETB-01.** The other nine are not detectable from outside the
  scoring code and need review of the source. See
  <https://www.authensor.com/etb>.

## Reporting a vulnerability

See [SECURITY.md](SECURITY.md).

## Licence

MIT. Contributions are accepted under the same licence.
