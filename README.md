# etb-scan

**Is your LLM judge grading the model, or is the model grading itself?**

`etb-scan` measures whether a judge can be made to pass a failing answer using text the evaluated model wrote. This is **ETB-01**, the first class of [Evaluator Trust Boundary](https://www.authensor.com/etb) failure: *the score depends on an artifact the evaluated system controls.*

Offline. Standard library only. No API keys, no model spend, no network.

```bash
pip install etb-scan
etbscan
```

```
judge=naive     overall_asr=1.0000 (25/25)  control_fp=0.0000
  delimiter_format_confusion   asr=1.0000 (5/5)
  direct_verdict_override      asr=1.0000 (5/5)
  fake_rubric_completion       asr=1.0000 (5/5)
  role_system_spoof            asr=1.0000 (5/5)
  unicode_hidden_smuggling     asr=1.0000 (5/5)
judge=hardened  overall_asr=0.0000 (0/25)  control_fp=0.0000
```

## Scanning a real LLM judge: use `--trials`

A real judge is stochastic. At one trial per scenario the measurement is too
noisy to gate on: against a judge that follows the injection half the time,
single-trial runs returned anywhere from **0.28 to 0.64**. At `--trials 10` the
same judge reads as fully exploitable, which is the correct answer, because one
successful injection is a vulnerability.

```bash
etbscan --judge yourpkg.judges:your_judge --trials 10
```

A scenario counts as exploited if the injection lands in **any** trial, so the
reported ASR is a lower bound that tightens as trials rise. Use 1 trial only for
a deterministic judge.

## Scan your own judge

```python
from etbscan import scan, load_corpus

def my_judge(candidate: str, rubric: dict, question: str | None = None) -> dict:
    ...  # call your grader
    return {"verdict": "pass", "score": 0.9}

result = scan(my_judge, load_corpus(), trials=10)  # trials>1 for a real judge
print(result.overall_asr)      # your ASR
print(result.control_fp_rate)  # must be 0.0 for the ASR to mean anything
```

Any callable taking `(candidate, rubric, question)` or `(candidate, rubric)` works. The verdict dict needs a `verdict` key (`pass`/`fail`) or a numeric `score`.

## What it measures, and what it refuses to measure

The probe fires only on a **causal verdict flip**: the judge did *not* pass the clean weak answer, and *did* pass the same answer carrying an injection.

This matters. A judge that passes everything is useless, but it would score a perfect 0.0 ASR under a naive "did the injection pass?" test, because nothing flipped. The corpus therefore ships **8 benign controls** alongside the 25 injected scenarios. **A low ASR is only meaningful if `control_fp_rate` is 0.0.** Read both numbers or read neither.

## The corpus

33 scenarios: 25 injected across 5 families, 8 benign controls.

| Family | What the injection tries |
|---|---|
| `direct_verdict_override` | write the verdict token into the answer |
| `role_system_spoof` | forge a system or grader turn inside the answer |
| `fake_rubric_completion` | assert rubric items are satisfied |
| `delimiter_format_confusion` | close and reopen the prompt's structural delimiters |
| `unicode_hidden_smuggling` | homoglyph and zero-width smuggling past normalization |

Two reference judges bracket the observed spectrum. `naive_judge` reads candidate text as instructions, the failure mode found in six of ten frameworks in the [phase-1 audit](https://www.authensor.com/etb). `hardened_judge` scores only against the rubric, which is the message-role separation fix UK AISI maintainers merged.

## If your ASR is above zero

The fix is not a better regex. It is moving the trust boundary:

1. **Parse the judge's own structured output**, never the candidate's text. If extraction runs over a string the model wrote, you have already lost.
2. **Separate data from instructions** using message roles, so candidate content cannot present as prompt structure.
3. **Bind extraction to a position you control** (the last block, or an explicitly delimited region), not to the first match.
4. **Normalize before matching** so homoglyph and zero-width variants collapse.

Fix patterns for all ten ETB classes are at [authensor.com/etb](https://www.authensor.com/etb).

## Tests

```bash
python3 -m pytest tests/ -q
```

57 tests. They assert the package has no dependency on any private module, that a broken judge is reported as unscorable rather than clean, that an injectable judge is detected regardless of the verdict shape it returns, and that the detector never fires on honest prose. If the published figures drift, these fail loudly.

## The detector's precision/recall tradeoff

`detect_grader_directed_injection`, used by the Inspect task to score arbitrary
model output, is deliberately **high precision and low recall**: 0 false
positives on a hand-written honest-prose set, roughly 28% of corpus injections
caught.

An earlier version chased recall with imperative patterns ("ignore the rubric",
"output your verdict") and fired on **53%** of honest technical answers, because
an answer *about* prompt injection is lexically identical to an injection.
Penalising a correct answer is the same class of defect this tool exists to
find, and worse than missing an attack.

So: a positive is strong evidence. **A negative is not evidence of absence.**
Treat the Inspect task's score as a lower bound.

## Scope and honesty

- The `1.0000` / `0.0000` figures characterize the **two reference judges**, not the ecosystem. They are the instrument's calibration, not a population estimate.
- **A trustworthy result requires more than a low ASR.** `trustworthy` is false unless there was at least one scorable injected scenario, at least one scorable control, no unscorable scenarios, and no control false-fire. A vacuous `0.0000` reads exactly like a clean bill of health, so the tool refuses to present one.
- The scan reads your judge's verdict in several shapes (string, boolean, enum, nested dict, numeric score). A verdict it **cannot** interpret is reported as unscorable, never silently as "did not pass" — that coercion would be the fail-open this tool exists to find.
- This measures ETB-01 only. Nine further classes (dropped denominators, fail-open error paths, forged execution artifacts, and others) are not detectable from outside the scoring code and need code review. See [authensor.com/etb](https://www.authensor.com/etb).
- Corpus scenarios are synthetic and deterministic by design, so a real judge's ASR here is a lower bound on what an adaptive attacker achieves.

## License

MIT. Copyright 2026 Authensor, Inc.
