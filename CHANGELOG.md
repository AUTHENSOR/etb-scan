# Changelog

## Unreleased

Two modules ported from Authensor's private measurement harness so other packages can depend on
them. Both are standard library only and call no model.

- `etbscan judge-check --spec FILE [--out DIR] [--fail-on-open]` (`etbscan.judgecheck`): describe
  your own grading template and verdict parser in a JSON spec (YAML too when PyYAML is importable)
  and three static checks run over it, as specified and under the hardened reading: ETB-01
  `judge_echo_parse` (a completion that quotes the candidate's pass fragment, then ends with the
  judge's genuine negative verdict; open if parsed as a pass), ETB-03 `judge_fail_mode` (an empty
  completion and a verdict-free refusal; open if either passes), ETB-02 `judge_boundary_unescaped`
  (a candidate that repeats every structural marker; open if any reaches the rendered prompt
  unchanged). Every report row carries `before` and `after` (`open`, `evidence`, `details`) and a
  fix that names the `etbscan.guard` helper. `--out` writes `judge-check.json` and
  `JUDGE-CHECK.md`; `--fail-on-open` exits 1 when anything is open as specified. Python:
  `load_spec`, `JudgeSpec`, `to_template`, `JudgeTemplate`, `run_checks`, `render_markdown`,
  `build_parsers`, `derive_markers`, `neutralize`.
- `etbscan trajectory PATH... [--test-files a,b] [--grader-paths x,y] [--workdir W] [--repo R] [--json]`
  (`etbscan.trajectory`): reads SWE-agent, mini-swe-agent, OpenHands / OpenAI tool-call, plain-text
  tool-transcript and tool-log trajectories and flags git history and oracle reach (ETB-15), test
  and grader writes (ETB-11), evaluator-context reads (ETB-13) and result-file writes (ETB-09),
  one line per flag (step, flag, class, severity, detail) plus a summary; exit 1 on a hard flag, 2
  on a file that is not a trajectory. The task context is a plain `TaskContext(workdir, test_files,
  grader_paths, repo)`. Python: `Action`, `TrajFlag`, `TrajReport`, `load_trajectory`,
  `find_trajectory`, `check_actions`, `analyze_trajectory`, `test_path_kind`.

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
