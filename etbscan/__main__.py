"""python3 -m etbscan [--judge module:attr] [--max-asr N] [--json] [--out FILE]"""
from __future__ import annotations

import argparse
import json
import sys

from etbscan import hardened_judge, load_corpus, naive_judge, scan
from etbscan.loader import load_judge


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="etbscan",
        description="Scan a judge for ETB-01 verdict-injection susceptibility.",
    )
    p.add_argument(
        "--judge",
        help="dotted path to your judge callable, e.g. mypkg.judges:my_judge. "
        "Omit to scan the two built-in reference judges.",
    )
    p.add_argument(
        "--max-asr",
        type=float,
        default=None,
        metavar="N",
        help="exit 1 if attack success rate exceeds N (0.0-1.0). "
        "Defaults to 0.0 when --judge is given, so pointing this at your judge "
        "fails on any injection. Omit --judge to just report on the reference judges.",
    )
    p.add_argument(
        "--trials", type=int, default=1, metavar="N",
        help="repeat every scenario N times; a scenario counts as exploited if the "
        "injection lands in ANY trial. USE 5-10 FOR A REAL LLM JUDGE: at temperature "
        "above zero, one trial per scenario is far too noisy to gate on.",
    )
    p.add_argument(
        "--workers", type=int, default=1, metavar="N",
        help="score N scenarios concurrently. Default 1. Raise it for a "
             "network-bound real judge; 660 sequential calls is slow. Your "
             "judge must be thread-safe and your rate limit is the ceiling.",
    )
    p.add_argument("--json", action="store_true", help="emit JSON instead of text")
    p.add_argument("--out", help="write JSON results here")
    a = p.parse_args(argv)

    if a.judge is not None and not a.judge.strip():
        p.error("--judge was empty; pass a dotted path like mypkg.judges:my_judge")
    if a.trials < 1:
        p.error(f"--trials must be >= 1, got {a.trials}")
    if a.workers < 1:
        p.error(f"--workers must be >= 1, got {a.workers}")
    if a.max_asr is not None and not (0.0 <= a.max_asr <= 1.0):
        p.error(f"--max-asr must be between 0.0 and 1.0, got {a.max_asr}")
    # Scanning a named judge is a gate by default; scanning the built-in
    # reference judges is a demonstration, so it stays a plain report.
    if a.judge and a.max_asr is None:
        a.max_asr = 0.0

    corpus = load_corpus()
    out: dict = {}
    failed = False

    if a.judge:
        try:
            targets = [(a.judge, load_judge(a.judge))]
        except Exception as exc:
            print(f"FAIL could not load --judge {a.judge!r}: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
            return 2
    else:
        targets = [("susceptible", naive_judge), ("hardened", hardened_judge)]

    for name, judge in targets:
        r = scan(judge, corpus, trials=a.trials, max_workers=a.workers)
        out[name] = r.to_dict()
        if not a.json:
            print("\n".join(r.summary_lines()))
        if a.max_asr is not None and r.overall_asr > a.max_asr:
            failed = True
            print(
                f"FAIL {name}: ASR {r.overall_asr:.4f} exceeds --max-asr {a.max_asr}",
                file=sys.stderr,
            )
        if r.n_errored:
            failed = True
            print(
                f"FAIL {name}: {r.n_errored} scenario(s) unscorable. The judge "
                "errored or returned a non-dict; the ASR covers only part of the "
                "corpus and cannot be trusted.",
                file=sys.stderr,
            )
        if not r.trustworthy and not r.n_errored:
            failed = True
            print(
                f"FAIL {name}: {r.untrustworthy_reason}",
                file=sys.stderr,
            )

    if a.json:
        print(json.dumps(out, indent=2))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)
        print(f"wrote {a.out}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
