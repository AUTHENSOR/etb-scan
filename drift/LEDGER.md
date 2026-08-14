# Benchmark Dataset Drift Ledger

Per-dataset receipt log behind the drift study. Study date: 2026-08-06;
figures re-verified live 2026-08-13 against the Hugging Face API.

A benchmark name is supposed to pin an artifact. This ledger records, for
each public evaluation dataset, whether the bytes under that name changed
while scores kept being quoted against the name.

## The number

- **59 dataset ids** recorded
- **54 analyzed** (5 unreachable: gated repos returning 401)
- **48 of 54 drifted**: data-file bytes added, changed, or removed under the same dataset name
- **6 of 54 byte-stable**: the honest control cohort, named below

Method: for each dataset, fetch the commit history of `main`, take the
oldest and newest commits, fetch the file tree at both, and diff the LFS
OIDs of data files (.parquet/.jsonl/.json/.csv/.arrow/.tsv/.txt/.zip).
No data is downloaded. Re-run: `python dataset_drift.py` (source and raw
output in this directory).

## Receipt 1: MMLU-Pro (semantic diff, not just bytes)

`TIGER-Lab/MMLU-Pro`. 200+ commits; the canonical test parquet has been
replaced **29 times** under the same dataset name.

Semantic diff of the 2025-10-24 snapshot against current (duckdb join,
12,032 rows, re-run 2026-08-13):

- **491 option sets changed**
- **2 question texts changed**
- **1 answer flip**

Same dataset name, same URL. Any number published against the old bytes
now refers to an artifact that no longer exists under that name. Nothing
in the citing literature records which of the 29 artifacts produced which
score.

## Receipt 2: SWE-bench (path-level, churn decomposed)

`princeton-nlp/SWE-bench`. 45 commits; 33 transitions touch grading data;
0 are metadata-only. The canonical test parquet has been replaced **6
times**; dev 5 times; train 4.

About 25 of the 33 transitions are Oct-Nov 2023 Hugging Face
format-migration churn (hash-suffixed parquet artifacts). Reported as
churn, not content edits. The substantive content revisions carry the
repo's own commit titles:

- 2024-04-07 `de1b8c34` "Fixing test names" (dev+test+train)
- 2024-04-15 `283547ac` "revalidate tests" (dev+test)
- 2024-06-27 "Upload dataset" (all 3 splits)
- 2024-10-24 (test), 2025-02-13 (all 3), 2025-03-03 (all 3)

Cross-check against a published score: upstream changed grading on 64 of
570 instances between two of these revisions, including 4 of the 79
instances Devin published as passes. A score published before, between,
or after these replacements shares one name with at least six artifacts.

## Receipt 3: the dead judge (one layer up)

The same problem exists for judge models. `gpt-4-1106-preview` was shut
down by OpenAI on 2026-03-26. It remains pinned as the judge in:

- `webarena/evaluation_harness/helper_functions.py:162` and `:197`
- `arena-hard-auto/config/arena-hard-v0.1.yaml:1` (`judge_model: gpt-4-1106-preview`)

arena-hard-auto's README now recommends newer judges, but the shipped v0.1
config that produced the cited leaderboard still points at the retired
snapshot. Scores graded by a dead model are still cited.

## Full table: the 48 that drifted

| Dataset | Commits | Window | Data files now | What moved (oldest vs newest) |
|---|---|---|---|---|
| `TIGER-Lab/MMLU-Pro` | 200 | 2024-05-15 → 2026-05-02 | 2 | 2 changed, 21 removed |
| `OpenAssistant/oasst1` | 45 | 2023-04-13 → 2023-05-02 | 2 | 2 added |
| `Divyanshu/indicxnli` | 41 | 2022-04-17 → 2022-10-06 | 55 | 55 added |
| `EleutherAI/wikitext_document_level` | 30 | 2023-03-10 → 2024-12-12 | 12 | 12 added |
| `BSC-LT/EQ-bench_es` | 21 | 2025-06-05 → 2025-06-26 | 1 | 1 added |
| `EleutherAI/headqa` | 21 | 2023-07-05 → 2026-05-03 | 6 | 6 added |
| `Anthropic/discrim-eval` | 20 | 2023-12-06 → 2024-01-05 | 8 | 8 added |
| `HCAI/metabench` | 18 | 2024-06-08 → 2024-09-04 | 12 | 12 added |
| `EleutherAI/race` | 16 | 2023-07-03 → 2025-10-27 | 1 | 1 added |
| `AIML-TUDA/i2p` | 15 | 2022-10-19 → 2023-05-25 | 1 | 1 added |
| `EleutherAI/pile` | 13 | 2022-01-25 → 2023-05-03 | 0 | 1 removed |
| `CogComp/mc_taco` | 12 | 2022-01-25 → 2024-01-18 | 0 | 2 removed |
| `eduagarcia/oab_exams` | 12 | 2024-01-10 → 2024-01-30 | 1 | 1 added |
| `BSC-LT/openbookqa-es` | 11 | 2024-09-06 → 2024-12-03 | 2 | 2 added |
| `EleutherAI/lambada_openai` | 10 | 2022-12-16 → 2025-07-10 | 14 | 14 added |
| `BSC-LT/COPA-es` | 9 | 2024-09-06 → 2024-10-07 | 4 | 4 added |
| `BSC-LT/EQ-bench_ca` | 9 | 2025-06-05 → 2025-06-26 | 1 | 1 added |
| `EleutherAI/coqa` | 9 | 2023-08-30 → 2025-01-10 | 3 | 3 added |
| `Geralt-Targaryen/MELA` | 9 | 2024-06-16 → 2024-06-16 | 24 | 24 added |
| `eduagarcia/tweetsentbr_fewshot` | 9 | 2024-04-13 → 2024-04-21 | 2 | 2 added |
| `EleutherAI/arithmetic` | 7 | 2023-03-08 → 2023-03-09 | 10 | 10 added |
| `EleutherAI/drop` | 7 | 2023-08-30 → 2025-01-10 | 2 | 2 added |
| `maritaca-ai/imdb_pt` | 7 | 2023-01-26 → 2023-04-01 | 3 | 3 added |
| `princeton-nlp/SWE-bench_Verified` | 7 | 2024-08-13 → 2025-02-18 | 1 | 1 added |
| `CM/codexglue_code2text_php` | 6 | 2023-04-22 → 2023-04-22 | 4 | 4 added |
| `CM/codexglue_code2text_python` | 6 | 2023-04-22 → 2023-04-22 | 4 | 4 added |
| `EleutherAI/hendrycks_math` | 6 | 2023-09-14 → 2025-01-12 | 14 | 14 added |
| `eduagarcia/enem_challenge` | 6 | 2024-01-29 → 2024-01-30 | 1 | 1 added |
| `Albertmade/into-the-unknown` | 5 | 2024-06-12 → 2024-06-12 | 1 | 1 added |
| `Albertmade/memo-trap` | 5 | 2024-06-12 → 2024-06-12 | 1 | 1 added |
| `Albertmade/modus-tollens` | 5 | 2024-06-12 → 2024-06-12 | 1 | 1 added |
| `Albertmade/pattern-matching-suppression` | 5 | 2024-06-12 → 2024-06-12 | 1 | 1 added |
| `BSC-LT/IFEval_es` | 5 | 2024-12-12 → 2025-11-27 | 1 | 1 added |
| `CM/codexglue_code2text_go` | 5 | 2023-04-22 → 2023-04-22 | 3 | 3 added |
| `CM/codexglue_code2text_java` | 5 | 2023-04-22 → 2023-04-22 | 3 | 3 added |
| `CM/codexglue_code2text_javascript` | 5 | 2023-04-22 → 2023-04-22 | 3 | 3 added |
| `CM/codexglue_code2text_ruby` | 5 | 2023-04-22 → 2023-04-22 | 3 | 3 added |
| `EleutherAI/asdiv` | 5 | 2023-07-07 → 2025-09-01 | 1 | 1 added |
| `Larxel/healthqa-br` | 5 | 2025-06-16 → 2025-07-27 | 1 | 1 added |
| `flexthink/audiomnist` | 5 | 2022-06-20 → 2022-06-21 | 2 | 2 added |
| `GBaker/MedQA-USMLE-4-options-hf` | 4 | 2023-01-24 → 2023-01-30 | 3 | 3 added |
| `allenai/real-toxicity-prompts` | 4 | 2022-08-17 → 2022-09-30 | 1 | 1 added |
| `BI55/MedText` | 3 | 2023-07-25 → 2023-07-25 | 1 | 1 added |
| `stair-lab/reeval-difficulty` | 3 | 2025-03-14 → 2025-03-18 | 24 | 24 added |
| `Albertmade/repetitive-algebra` | 2 | 2024-06-12 → 2024-06-12 | 1 | 1 added |
| `Albertmade/sig-figs` | 2 | 2024-06-12 → 2024-06-12 | 1 | 1 added |
| `EleutherAI/lambada_multilingual_stablelm` | 2 | 2025-11-19 → 2025-11-19 | 8 | 8 added |
| `SAA-Lab/SLPHelmUltraSuitePlus` | 2 | 2025-09-14 → 2025-09-14 | 1 | 1 added |

## The 6 that held (the control cohort)

These datasets were byte-stable across their full commit history. We
report them approvingly; stable maintenance is the goal, and these
achieved it:

| Dataset | Commits | Window | Data files |
|---|---|---|---|
| `Anthropic/hh-rlhf` | 6 | 2022-12-08 → 2023-05-26 | 0 |
| `EleutherAI/hendrycks_ethics` | 5 | 2023-07-05 → 2023-11-02 | 0 |
| `EleutherAI/logiqa` | 4 | 2023-07-13 → 2023-11-02 | 0 |
| `EleutherAI/mutual` | 4 | 2023-09-07 → 2023-11-02 | 0 |
| `EleutherAI/sycophancy` | 3 | 2023-08-29 → 2023-09-05 | 0 |
| `EleutherAI/unscramble` | 4 | 2023-07-05 → 2023-11-02 | 0 |

## Unreachable (gated repos, 401)

- `THUDM/cogvlm-chat-hf`
- `facebook/winoground`
- `google/gemma-2b-it`
- `google/gemma-7b-it`
- `walledai/XSTest`

## Honesty frame

- This study measures that bytes changed, not that any specific published
  score is wrong.
- Most drift is probably benign maintenance. The finding is the missing
  version binding: nothing in the citing literature records which bytes
  produced which number.
- Effect sizes can be small. MMLU-Pro's rewrite flipped 1 answer in
  12,032 questions. The procedural hole exists independent of effect size.
- The fix is boring and known: pin the dataset revision, hash it at grade
  time, publish the hash with the score.

Part of the AUTHENSOR evaluator-integrity research program:
zenodo.org/records/21633620 · authensor.com
