# Changelog

## Unreleased

Precision pass on `etbscan lint`, calibrated against a 2026-11 survey that ran the 0.2.0 lint
over 31 public evaluation frameworks. `tests/test_lint.py` now carries every confirmed hit and
every false positive quoted in that survey as a fixture, so the calibration is a test, not a note.

- `ETB-01-FIRST-MATCH`: a regex must name a verdict token to count (`yes|no`, `A|B|C`, `PASS|FAIL`
  as whole words or next to a count, `correct:` / `INCORRECT`, `score` / `rating` / `grade` /
  `verdict`, `[[n]]`). `PASSWORD`, `"Failed password"`, `scores_*.json` and a CI `failure`
  condition no longer fire. A bare letter class (`[A-D]`) applied to the candidate's own answer
  (`pred`, `output_text`, "final answer is") is answer extraction for exact match, not a verdict
  parse, and is skipped. A `^` / `\A` anchor without `re.M` (or a lazy `.*?` after it) binds the
  parse positionally and is treated like an end anchor. Every confirmed survey hit still fires:
  simple-evals, FastChat, HELM `<score>`, lighteval `[[n]]` / `<score>`, the harbor judges, the
  inspect_evals copies, preparedness `N passing`.
- `ETB-01-SUBSTRING-ORDER`: an `if` / `elif` chain is reported once, at its head, instead of once
  per `elif` (FastChat `common.py` 283 and 285 were one finding).
- `ETB-03-DEFAULT-PASS`: fires only where the defaulted value is returned, assigned or passed on
  in grading context, meaning an enclosing function, class or module named like grade / score /
  judge / verdict / parse / evaluate / metric / reward / correct / pass, or an assignment target,
  keyword or dict key named like that; never when both branches are constants
  (`False if flag else True`). The survey's 37 hits (config flags, file modes, fixtures, log
  strings) all go silent; the grader shapes in the tests still fire.
- `ETB-11-RESTORE-FAILS-OPEN`: new shape, severity medium: a per-path restore whose failure is
  swallowed, `git checkout <ref> -- "$p" 2>/dev/null || true` (SWE-bench Pro v2 `test.sh`),
  reported whether or not the script runs under `set -e`.
- `--json` now emits one object (`tool`, `files_scanned`, `counts` by severity, `findings`)
  instead of a bare list of findings; the text summary line carries the file count too.
- `SyntaxWarning`s raised while parsing linted third-party files are no longer printed.
- Python API: `run_lint(paths) -> LintReport` (findings plus `files_scanned`); `lint_paths` and
  `lint_source` are unchanged.

## 0.2.0

`etbscan lint` (static rules for grader and verifier code) and `etbscan.guard` (drop-in
hardening helpers). See the git history for earlier releases.
