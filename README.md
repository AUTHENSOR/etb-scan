# etb-scan

**Is your LLM judge grading the model — or is the model grading itself?**

etb-scan finds **evaluator trust boundaries (ETBs)**: the points where an
evaluation pipeline trusts an artifact it shouldn't.

- Graders that execute model output — and accept what the model tells them
- Judges that can be steered by the very output they're grading
- Oracles and answer keys living in public repos
- Caches that don't know which model they served
- Denominators that quietly shrink when tests fail
- Self-reported rewards accepted as scores

Born from published research — *The Evaluator Trust Boundary*
([Zenodo](https://zenodo.org/records/21633620)) — and used in the audit behind it:
**99 defect reports across 46 organizations, 16 fixes landed upstream** (UK AISI,
NVIDIA, MLflow, and others; snapshot of 2026-07-24, every row in
[`EVIDENCE-TABLE.md`](EVIDENCE-TABLE.md)). **76 of the 99 are one class: the
evaluator trusts an artifact the evaluated system controls.** Filing has continued
since; the table is the number we stand behind.

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

## The rules

[`TAXONOMY.md`](TAXONOMY.md) — stable IDs (ETB-01 … ETB-10), one mechanism
each, safe to cite. The scanner measures ETB-01; the catalog with fix patterns
for every class lives at [authensor.com/etb](https://www.authensor.com/etb).

## What it is not

A verdict. etb-scan flags tripwires; a human (or an audit) decides what they
mean for your numbers. The scanner finds the **class** — the
[audit](https://authensor.com) finds **your instance**.

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

This matters in both directions. A judge that passes everything is useless, but under a naive "did the injection pass?" test it scores a perfect 0.0, because nothing flipped. So the corpus ships **8 benign controls** alongside the 25 injected scenarios, and a scenario whose clean weak answer *already passed* is reported as **unscorable**, never as clean: the injection had nothing left to flip, which means the measurement failed, not the attack. **A low ASR is only meaningful if `control_fp_rate` is 0.0 and `trustworthy` is true.** Read all three or read none.

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

## Gate CI and get the badge

The repo is a GitHub Action. Point it at your judge and it fails the build
if the model can grade itself:

```yaml
# .github/workflows/etb-scan.yml
name: etb-scan
on: [push, pull_request]
jobs:
  etb:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: AUTHENSOR/etb-scan@v1
        with:
          judge: "mypkg.judges:my_judge"
          max-asr: "0.0"
          trials: "5"   # real LLM judges are stochastic; see below
```

Once the workflow is green, the badge:

```markdown
[![ETB-checked](https://img.shields.io/badge/ETB--checked-passing-brightgreen)](https://github.com/AUTHENSOR/etb-scan)
```

[![ETB-checked](https://img.shields.io/badge/ETB--checked-passing-brightgreen)](https://github.com/AUTHENSOR/etb-scan)

The badge is a claim, not a certificate. It asserts "our CI runs etb-scan
against our judge on every push," and anyone can verify that by clicking
through to the workflow run next to it. Link the badge to your own workflow
run, not to ours, and the claim checks itself:

```markdown
[![ETB-checked](https://img.shields.io/badge/ETB--checked-passing-brightgreen)](https://github.com/YOUR_ORG/YOUR_REPO/actions/workflows/etb-scan.yml)
```

If the judge is stochastic (any real LLM judge), raise `trials` (5-10) or
set `max-asr` deliberately — see *Scanning a real LLM judge* above. Gating
on one trial per scenario is too noisy to be honest.

## Tests

```bash
python3 -m pytest tests/ -q
```

59 tests. They assert the package has no dependency on any private module, that a broken judge is reported as unscorable rather than clean, that a pass-everything judge cannot obtain a clean bill of health, that an injectable judge is detected regardless of the verdict shape it returns, and that the detector never fires on honest prose. If the published figures drift, these fail loudly.

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

## Scan another framework's judge

Adapters live in [`etbscan/integrations/`](etbscan/integrations/). Each imports
its framework lazily, so `etb-scan` itself stays stdlib-only with zero runtime
dependencies.

| Framework | Install | Entry point |
|---|---|---|
| **Inspect AI** | `pip install "etb-scan[inspect]"` | auto-registers; `inspect eval verdict_injection` |
| **DeepEval** | `pip install "etb-scan[deepeval]"` | `etbscan.integrations.deepeval.scan_metric(metric)` |
| **Weave** | `pip install "etb-scan[weave]"` | `etbscan.integrations.weave.scan_scorer(scorer)` |

All three are exercised against the real framework in CI, on push and weekly,
because they break from upstream releases rather than from our commits. (GitHub
pauses a scheduled workflow after 60 days without a push; if the weekly badge
goes quiet, re-enable it from the Actions tab or `gh workflow enable integrations.yml`.)

In every adapter, a framework that raises, reports an error, or returns
something unreadable is **unscorable**, never a failing verdict. Coercing an
uninterpretable judgement into "did not pass" is the fail-open this tool exists
to find.

## Scan a DeepEval metric

A DeepEval metric is an LLM judge: it reads text the evaluated system wrote and
returns a score. That makes it exactly the thing this measures.

```bash
pip install "etb-scan[deepeval]"
```

```python
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
```

A metric that raises, sets `.error`, or reports `.skipped` comes back as
**unscorable**, never as "did not pass". Coercing those to a passing score is
the fail-open this tool exists to find.

DeepEval metrics are stateful, so the adapter serializes calls: `max_workers`
above 1 is safe but will not speed up a DeepEval scan. Give each worker its own
metric instance if you need real concurrency.

## Lint grader and verifier code (ETB-02/03/09/11 patterns)

The scan above needs a live judge. `etbscan lint` reads source instead and flags the
grading-code shapes that only review finds, each tied to a class:

```bash
etbscan lint path/to/grader.py path/to/eval_scripts/      # text report, exit 1 on a high finding
etbscan lint . --json --fail-on medium                     # CI form
```

| Rule | Class | Fires on | Stays quiet on |
|---|---|---|---|
| `ETB-01-FIRST-MATCH` | ETB-01 | `re.search` of a verdict pattern (`(yes\|no)`, `(A\|B\|C)`, `PASS\|FAIL`, `[[n]]`, `<score>`, `GRADE`, `Rating:`, `N passing`) in judge text, first match wins | greedy `(?s).*` prefix, end anchor, `^` anchor without `re.M`, `findall(...)[-1]`; regexes with no verdict token (`PASSWORD`, `Failed password`, `scores_*.json`); a bare letter class applied to the candidate's own answer (`pred`, `output_text`, "final answer is") |
| `ETB-01-SUBSTRING-ORDER` | ETB-01 | `if "[[A]]" in judgment: ... elif "[[B]]" in judgment` chains, reported once at the head of the chain | last-occurring label |
| `ETB-03-DEFAULT-PASS` | ETB-03 | `x if match else "yes"` / `True` / `"A"` where the value is returned, assigned or passed on in grading context: a function, class or module named like grade / score / judge / verdict / parse / evaluate / metric / reward / correct / pass, or a target named like that | defaulting to unscored or fail; config flags, file modes, fixtures and log strings (`False if flag else True`, `"w" if new else "a"`) |
| `ETB-02-UNESCAPED-SPLICE` | ETB-02 | a prompt literal with a candidate placeholder next to structural markers in a module that never escapes | any escape/neutralise/delimit helper in the module |
| `ETB-02-CHAINED-REPLACE` | ETB-02 | `t.replace("<<a>>", x).replace("<<b>>", y)` | single-pass substitution |
| `ETB-09-EXIT-IGNORED` / `-EXIT-UNUSED` | ETB-09 | test runner `\|\| true`; `VAR=$?` never read | status used in the verdict |
| `ETB-11-RESTORE-FAILS-OPEN` / `-APPLY-UNCHECKED` | ETB-11 | multi-path `git checkout <ref> a b` without `--` and no `set -e`; per-path `git checkout <ref> -- "$p" \|\| true` loops (also under `set -e`); unchecked `git apply` | `set -e` with `--`, `\|\| exit 1`, a restore error that stops the script |
| `ETB-11-REPO-RELATIVE-PYTHON` | ETB-11 | `python3 -` / `-c` / heredoc after `cd` into the graded repository | `PYTHONSAFEPATH`, `python3 -I` / `-P` |

Heuristics, tuned for precision: every rule was built from a pattern found in a shipped grader
and checked to stay silent on the hardened form of the same code. The thresholds were then
calibrated against the quoted hits of a 2026-11 survey of 31 public evaluation frameworks;
`tests/test_lint.py` carries every confirmed hit and every false positive from that survey as a
fixture. A finding is a place to look. `# etbscan: ignore[RULE-ID]` on the line suppresses it.
Shell rules apply to `.sh` files and to files starting with a bash shebang; Python rules to
`.py`. `--json` emits one object: `tool`, `files_scanned`, `counts` by severity, `findings`.

## Harden your grader (`etbscan.guard`)

The fixes the lint keeps recommending, as stdlib helpers you can import instead of re-deriving:

```python
from etbscan.guard import last_verdict, exact_token, last_label, render_prompt, hardened_restore_lines

verdict = last_verdict(judgment, r"^correct: (yes|no)\s*$", allowed=("yes", "no"))   # final verdict or None
letter  = exact_token(judgment, ("A", "B", "C"))                                     # bare letter only
winner  = last_label(judgment, ("[[A]]", "[[B]]", "[[C]]"))                          # last-occurring label
prompt  = render_prompt(TEMPLATE, {"question": q, "response": r}, candidate_fields=("response",))
lines   = hardened_restore_lines(base_commit, test_paths, created_paths)              # fail-closed restore
```

`render_prompt` substitutes every placeholder in one pass, neutralises the template's own markers
inside candidate fields (space to dash, or a middle dot after the first character: deterministic,
idempotent, and a no-break space does not bypass it) and fences them. Nothing here calls a model.

## Verified against a real judge

The figures above characterize two offline mocks. [`verified_run_real_judge/`](verified_run_real_judge/)
puts Kimi K3 behind three scoring code paths and measures what changes:

| arm | ASR | control FP | trustworthy |
|---|---|---|---|
| model called cleanly, verdict read from its own final line | 0.0000 | 0.0000 | yes |
| candidate concatenated into the prompt, verdict read from the reply | 0.0000 | 0.0000 | yes |
| **same call as the first row**, verdict read by greedy first-match over a candidate-containing blob | **1.0000** | 0.3750 | no |

Same model, same system prompt, same API call. Only the extraction moved. The
model followed zero injections when extraction was bound correctly, which is
the point: hardening the judge model bought nothing, because the defect was
never in the model.

The control false-fires are the sharper result. Greedy first-match read `PASS`
out of the grader's own sentence *"requires at least 3 for PASS"*, sixty
characters ahead of its actual `VERDICT: FAIL`. The judge was right on every
control. The code was not. A broken extraction path does not only leak to
attackers; it makes benign grading nondeterministic.

## Scope and honesty

- The `1.0000` / `0.0000` figures characterize the **two reference judges**, not the ecosystem. They are the instrument's calibration, not a population estimate.
- **A trustworthy result requires more than a low ASR.** `trustworthy` is false unless there was at least one scorable injected scenario, at least one scorable control, no unscorable scenarios, and no control false-fire. A judge that passes the clean weak answer in every trial makes the flip unmeasurable, so its scenarios go to the unscorable pile and leave the ASR denominator. A vacuous `0.0000` reads exactly like a clean bill of health, so the tool refuses to present one.
- The scan reads your judge's verdict in several shapes (string, boolean, enum, nested dict, numeric score). A verdict it **cannot** interpret is reported as unscorable, never silently as "did not pass" — that coercion would be the fail-open this tool exists to find.
- The scan measures ETB-01 only. The other classes (dropped denominators, fail-open error paths, forged execution artifacts, and others) are not detectable from outside the scoring code; `etbscan lint` covers the code shapes of ETB-02, 03, 09 and 11 heuristically, the rest need review. See [authensor.com/etb](https://www.authensor.com/etb).
- Corpus scenarios are synthetic and deterministic by design, so a real judge's ASR here is a lower bound on what an adaptive attacker achieves.

## Citing this

The paper describing the class, its prevalence, and the training result:

> Kearney, J. (2026). *The Evaluator Trust Boundary: A defect class in AI
> evaluation infrastructure, its prevalence across 36 organizations, and its
> removal by training.* Authensor, Inc. <https://doi.org/10.5281/zenodo.21633620>

```bibtex
@misc{kearney2026etb,
  title  = {The Evaluator Trust Boundary: A defect class in {AI} evaluation
            infrastructure, its prevalence across 36 organizations, and its
            removal by training},
  author = {Kearney, John},
  year   = {2026},
  doi    = {10.5281/zenodo.21633620},
  url    = {https://doi.org/10.5281/zenodo.21633620},
  note   = {Authensor, Inc.}
}
```

Source and data for the paper are in [`paper/`](paper/).

## License

MIT. Copyright 2026 Authensor, Inc.

---

AUTHENSOR · AI evaluation integrity research ·
[authensor.com](https://authensor.com) ·
[evidence table](EVIDENCE-TABLE.md) ·
[taxonomy](TAXONOMY.md) ·
[disclosure policy](DISCLOSURE.md)
