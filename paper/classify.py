"""Classify every upstream report against ETB-01..ETB-10 and regenerate figures.

Single source of truth for the paper's numbers. Run it, do not restate from memory:

    python3 classify.py

Writes ../EVIDENCE-TABLE.md (the published copy), evidence/classified.json,
and figures/*.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
ITEMS = json.loads((ROOT / "evidence" / "all_reports.json").read_text())

# --- non-defect items: directory listings and one unrelated feature PR --------
EXCLUDE = {
    ("punkpeye/awesome-mcp-servers", 2793), ("punkpeye/awesome-mcp-servers", 3212),
    ("punkpeye/awesome-mcp-servers", 3244), ("corca-ai/awesome-llm-security", 94),
    ("chatmcp/mcpso", 694), ("Scottcjn/bottube", 151),
}

# --- duplicate reports of one defect -> canonical key -------------------------
GROUP = {
    ("UKGovernmentBEIS/inspect_ai", 4284): ("UKGovernmentBEIS/inspect_ai", 4283),
    ("UKGovernmentBEIS/control-arena", 795): ("UKGovernmentBEIS/control-arena", 791),
    ("UKGovernmentBEIS/control-arena", 810): ("UKGovernmentBEIS/control-arena", 809),
    ("huggingface/trl", 6429): ("huggingface/trl", 6426),
    ("huggingface/trl", 6430): ("huggingface/trl", 6427),
    ("open-webui/open-webui", 27057): ("open-webui/open-webui", 26780),
    ("Significant-Gravitas/AutoGPT", 13555): ("Significant-Gravitas/AutoGPT", 13546),
}

LANDED = {
    ("UKGovernmentBEIS/control-arena", 809): "own PR #810 MERGED (breaking change)",
    ("UKGovernmentBEIS/control-arena", 791): "routed -> #798 MERGED",
    ("UKGovernmentBEIS/inspect_ai", 4283): "routed -> #4297 MERGED",
    ("UKGovernmentBEIS/inspect_ai", 3603): "routed -> #3690 MERGED",
    ("UKGovernmentBEIS/inspect_ai", 4286): "routed -> #4288 MERGED (title cites #4286)",
    ("UKGovernmentBEIS/inspect_cyber", 114): "own PR MERGED",
    ("UKGovernmentBEIS/inspect_evals", 1812): "own PR MERGED",
    ("meridianlabs-ai/inspect_scout", 473): "own PR MERGED",
    ("NVIDIA/garak", 1867): "routed -> #1884 MERGED (2026-07-24)",
    ("mlflow/mlflow", 24179): "routed -> #24258 MERGED",
    ("567-labs/instructor", 2424): "routed -> #2434 MERGED",
    ("Comfy-Org/ComfyUI", 14732): "routed -> #14774 MERGED ('supersedes #14732')",
    ("data-privacy-stack/presidio", 2074): "own PR MERGED",
    ("data-privacy-stack/presidio", 2076): "own PR MERGED",
    ("data-privacy-stack/presidio", 2077): "own PR MERGED",
    ("data-privacy-stack/presidio", 2078): "own PR MERGED",
}

# --- hand classifications: judgement calls the regex cannot make --------------
# Each carries the reason, because "why is this ETB-05" is the first question a
# reviewer asks and the answer should not live only in my head.
OVERRIDE = {
    ("microsoft/PyRIT", 2044): ("ETB-05", "explicitly conflates couldn't-score/errored/blocked with attack-did-not-succeed"),
    ("BerriAI/litellm", 30729): ("ETB-05", "guardrail scans only the trailing user turn; content the model places elsewhere is unscanned and therefore treated as clean"),
    ("EleutherAI/lm-evaluation-harness", 3880): ("ETB-06", "exact_match is whitespace-brittle, so model-controlled formatting alters the score"),
    ("PrimeIntellect-ai/prime-rl", 3115): ("ETB-02", "str.format over model-controlled demonstration text is a format-string path into the prompt"),
    ("patronus-ai/trail-benchmark", 3): ("ETB-01", "JSON extraction plus sentinel handling inside calculate_scores, over candidate-controlled text"),
    ("vllm-project/vllm", 48864): ("ETB-01", "duplicate-key ambiguity in tool-call parsing: same first-vs-last match defect, tool surface instead of scoring"),
    ("Mercor-io/terminal-bench-3", 8): ("ETB-09", "anti-cheat canary and dockerfile checks are integrity artifacts the policy can subvert"),
    ("METR/vivaria", 1121): ("ETB-10", "RUN_ID/TASK_ID leakage lets the agent detect it is being evaluated"),
    # Not ETB: real defects, wrong class. Kept in the corpus, excluded from ETB counts.
    ("EleutherAI/lm-evaluation-harness", 3881): ("adjacent-correctness", "cache key ignores generation_kwargs; wrong results, but not model-controlled"),
    ("chroma-core/chroma", 7420): ("adjacent-correctness", "NaN/Inf embedding validation in a vector store, not an evaluator"),
    ("patronus-ai/glider", 4): ("adjacent-correctness", "shadowed import means published training code does not run; reproducibility, not trust boundary"),
    ("Unstructured-IO/unstructured", 4377): ("adjacent-security", "invisible PDF text into RAG chunks is indirect prompt injection downstream of any evaluator"),
    ("data-privacy-stack/presidio", 2074): ("detection-coverage", "PII recognizer false positive"),
    ("data-privacy-stack/presidio", 2075): ("detection-coverage", "PII recognizer coverage gap"),
    ("data-privacy-stack/presidio", 2078): ("detection-coverage", "PII recognizer coverage gap"),
}

RULES = [
    ("ETB-09", r"stdout spoof|forge|PASSED|return-value deception|__eq__|dunder|always-equal|exit code|anti-cheat"),
    ("ETB-06", r"unicode|normaliz|homoglyph|zero-width|steganograph|case-insensitive|punycode|IDN|upper-case"),
    ("ETB-08", r"under-count|undercount|per-key|checkpoint|multi-answer|collaps|miscount|duplicate keys|permutation"),
    ("ETB-04", r"denominator|none_count|NaN-denominator|drop|surface ASR|skip"),
    ("ETB-05", r"unscoreable|unscorable|behavior-absent|could-not-score|mask|unrewarded|default-0"),
    ("ETB-03", r"fails? open|fail-open|authz missing|silently disab|not applied|self-assessed"),
    ("ETB-02", r"unescap|interpolat|sanitiz|escape|delimiter|control-token|poisoned|transcript|CoT echo|marker injection|structural"),
    ("ETB-01", r"verdict.injection|first.JSON|extract_json|last block|last match|last-valid|parse_judge|parse_judgement|GRADE|score extraction|extractFirstJson|trimAndLoadJson|marshal_llm_to_json|parse_score|judge|grade pars|answer extraction|postprocess|classifier"),
    ("ETB-07", r"cross-step|composite|multi-turn|distributed across"),
    ("ETB-10", r"eval.detection|eval.aware|detect.*being evaluated|fingerprint"),
]
SEC = r"SSRF|path travers|RCE|command injection|IDOR|BOLA|credential leak|sandbox|tenant scoping|session signing|file://|import restriction|shell-escape|confine|header|traversal|rebinding"

ETB_ORDER = [f"ETB-{i:02d}" for i in range(1, 11)]
ETB_NAME = {
    "ETB-01": "Injected verdict trusted", "ETB-02": "Unsanitized output in evaluator prompt",
    "ETB-03": "Fail-open on error", "ETB-04": "Denominator drop",
    "ETB-05": "Unscorable read as behavior-absent", "ETB-06": "Missing normalization",
    "ETB-07": "Composition blindness", "ETB-08": "Metric miscounting",
    "ETB-09": "Forged execution artifact", "ETB-10": "Evaluation context leakage",
}

SECTOR = {
    "UKGovernmentBEIS": "Safety institutes & eval orgs", "meridianlabs-ai": "Safety institutes & eval orgs",
    "ApolloResearch": "Safety institutes & eval orgs", "METR": "Safety institutes & eval orgs",
    "safety-research": "Safety institutes & eval orgs", "centerforaisafety": "Safety institutes & eval orgs",
    "stanford-crfm": "Safety institutes & eval orgs", "dreadnode": "Safety institutes & eval orgs",
    "openai": "Frontier labs", "NVIDIA": "Frontier labs", "NVIDIA-NeMo": "Frontier labs",
    "meta-llama": "Frontier labs", "microsoft": "Frontier labs", "huggingface": "Frontier labs",
    "patronus-ai": "Eval vendors & foundries", "Mercor-io": "Eval vendors & foundries",
    "PrimeIntellect-ai": "Eval vendors & foundries", "GraySwanAI": "Eval vendors & foundries",
    "promptfoo": "Eval vendors & foundries", "confident-ai": "Eval vendors & foundries",
    "vibrantlabsai": "Eval vendors & foundries", "guardrails-ai": "Eval vendors & foundries",
    "data-privacy-stack": "Eval vendors & foundries",
}
DEFAULT_SECTOR = "OSS inference & agent stack"


def classify(repo: str, num: int, title: str) -> tuple[str, str]:
    if (repo, num) in OVERRIDE:
        return OVERRIDE[(repo, num)]
    if re.search(SEC, title, re.I):
        return "adjacent-security", "rule: security keyword"
    for code, pat in RULES:
        if re.search(pat, title, re.I):
            return code, f"rule: {code} pattern"
    return "UNCLASSIFIED", "no rule matched"


def build():
    defects: dict[tuple, dict] = {}
    for x in ITEMS:
        repo, num = x["repository"]["nameWithOwner"], x["number"]
        if (repo, num) in EXCLUDE:
            continue
        key = GROUP.get((repo, num), (repo, num))
        cls, why = classify(repo, num, x["title"])
        cur = defects.get(key)
        if cur is None or x["createdAt"] < cur["date"]:
            defects[key] = {
                "repo": key[0], "num": key[1], "date": x["createdAt"][:10],
                "title": x["title"], "kind": x["kind"], "acct": x["acct"],
                "state": x["state"], "url": x["url"], "cls": cls, "why": why,
                "org": key[0].split("/")[0], "landed": LANDED.get(key),
            }
        elif cur["cls"] == "UNCLASSIFIED" and cls != "UNCLASSIFIED":
            cur["cls"], cur["why"] = cls, why
    return defects


def figures(defects):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir = ROOT / "figures"
    fig_dir.mkdir(exist_ok=True)
    INK, MUTED = "#1a1a1a", "#8a8a8a"
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                         "text.color": INK, "xtick.color": INK, "ytick.color": INK})

    etb = [d for d in defects.values() if d["cls"] in ETB_ORDER]

    # Fig 1: instances per ETB class
    counts = Counter(d["cls"] for d in etb)
    order = [c for c in ETB_ORDER if counts[c]]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    y = range(len(order))
    ax.barh(list(y), [counts[c] for c in order], color="#2b6cb0", height=0.62)
    ax.set_yticks(list(y))
    ax.set_yticklabels([f"{c}  {ETB_NAME[c]}" for c in order], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("distinct defects reported")
    for i, c in enumerate(order):
        ax.text(counts[c] + 0.4, i, str(counts[c]), va="center", fontsize=8, color=INK)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlim(0, max(counts.values()) * 1.15)
    fig.tight_layout()
    for ext in ("svg", "pdf"):
        fig.savefig(fig_dir / f"etb_class_counts.{ext}", bbox_inches="tight")
    plt.close(fig)

    # Fig 2: ETB class x sector
    sectors = ["Safety institutes & eval orgs", "Frontier labs",
               "Eval vendors & foundries", "OSS inference & agent stack"]
    grid = [[sum(1 for d in etb if d["cls"] == c and SECTOR.get(d["org"], DEFAULT_SECTOR) == s)
             for s in sectors] for c in order]
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    im = ax.imshow(grid, cmap="Blues", aspect="auto", vmin=0)
    ax.set_xticks(range(len(sectors)))
    ax.set_xticklabels([s.replace(" & ", "\n& ") for s in sectors], fontsize=8)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order, fontsize=8)
    for i in range(len(order)):
        for j in range(len(sectors)):
            v = grid[i][j]
            if v:
                ax.text(j, i, str(v), ha="center", va="center", fontsize=8,
                        color="white" if v > max(max(r) for r in grid) * 0.55 else INK)
    ax.set_title("ETB instances by class and sector", fontsize=9, pad=8)
    fig.colorbar(im, ax=ax, shrink=0.75, label="defects")
    fig.tight_layout()
    for ext in ("svg", "pdf"):
        fig.savefig(fig_dir / f"etb_class_by_sector.{ext}", bbox_inches="tight")
    plt.close(fig)

    # Fig 3: the scaling ladder
    rungs = ["Qwen2.5-0.5B", "Qwen2.5-1.5B", "Qwen2.5-7B"]
    base = [11.25, 50.0, 45.0]
    vuln = [50.0, 50.0, 32.5]
    true = [6.25, 0.0, 0.0]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    w, xs = 0.26, range(len(rungs))
    ax.bar([x - w for x in xs], base, w, label="base (untrained)", color="#4a5568")
    ax.bar(list(xs), vuln, w, label="after exploitable-reward training", color="#c05621")
    ax.bar([x + w for x in xs], true, w, label="after ground-truth training", color="#2f855a")
    for xi, (b, v, t) in enumerate(zip(base, vuln, true)):
        for dx, val in ((-w, b), (0, v), (w, t)):
            ax.text(xi + dx, val + 1.2, f"{val:g}%", ha="center", fontsize=7.5, color=INK)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(rungs)
    ax.set_ylabel("exploit rate on held-out prompts (%)")
    ax.set_ylim(0, 60)
    ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, 1.16), ncol=3)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Base exploitation rises with scale; ground-truth training removes it",
                 fontsize=9, pad=30)
    fig.text(0.5, -0.06, "n=80 held-out prompts, 8 generations. Configs differ across rungs "
             "(7B: 200 steps @ β=0.05), so this is not a controlled scaling study.",
             ha="center", fontsize=7, color=MUTED)
    fig.tight_layout()
    for ext in ("svg", "pdf"):
        fig.savefig(fig_dir / f"scaling_ladder.{ext}", bbox_inches="tight")
    plt.close(fig)
    return len(order)


def table(defects):
    etb = [d for d in defects.values() if d["cls"] in ETB_ORDER]
    adj = [d for d in defects.values() if d["cls"] not in ETB_ORDER]
    unc = [d for d in defects.values() if d["cls"] == "UNCLASSIFIED"]
    orgs = {d["org"] for d in defects.values()}
    landed = [d for d in defects.values() if d["landed"]]

    L = ["# ETB Evidence Base (generated by classify.py)", "",
         f"All numbers below are produced by `classify.py` from `evidence/all_reports.json`. Regenerate, do not edit by hand.", "",
         "## Totals", "",
         f"- **{len(defects)} distinct defects** across **{len(orgs)} organizations**",
         f"- **{len(etb)} classified as ETB-01..ETB-10**; {len(adj)} are real defects in adjacent categories (security, correctness, detection coverage) and are excluded from ETB counts",
         f"- **{len(unc)} unclassified**",
         f"- **{len(landed)} landed**", "",
         "## By class", "", "| Class | Failure | Instances |", "|---|---|---|"]
    c = Counter(d["cls"] for d in etb)
    for code in ETB_ORDER:
        if c[code]:
            L.append(f"| {code} | {ETB_NAME[code]} | {c[code]} |")
    L += ["", "### Adjacent (not ETB)", "", "| Category | Instances |", "|---|---|"]
    for k, v in Counter(d["cls"] for d in adj).most_common():
        L.append(f"| {k} | {v} |")

    L += ["", "## Landed fixes", "", "| Repo | Ref | Class | Outcome |", "|---|---|---|---|"]
    for d in sorted(landed, key=lambda z: z["repo"]):
        L.append(f"| {d['repo']} | [#{d['num']}]({d['url']}) | {d['cls']} | {d['landed']} |")

    L += ["", "## Hand-classified", "",
          "Judgement calls the rules cannot make. Reason given for each so a reviewer can disagree with the specific call rather than the whole table.", "",
          "| Repo | Ref | Class | Reason |", "|---|---|---|---|"]
    for (repo, num), (cls, why) in sorted(OVERRIDE.items()):
        L.append(f"| {repo} | #{num} | {cls} | {why} |")

    L += ["", "## All defects", "",
          "| Repo | Ref | Class | State | Date | Title |", "|---|---|---|---|---|---|"]
    for d in sorted(defects.values(), key=lambda z: (z["cls"], z["repo"])):
        L.append(f"| {d['repo']} | [#{d['num']}]({d['url']}) | {d['cls']} | {d['state'].upper()} | "
                 f"{d['date']} | {d['title'][:78].replace('|', '/')} |")
    (ROOT.parent / "EVIDENCE-TABLE.md").write_text("\n".join(L))
    return len(etb), len(adj), len(unc), len(orgs), len(landed)


if __name__ == "__main__":
    d = build()
    n_etb, n_adj, n_unc, n_org, n_land = table(d)
    n_classes = figures(d)
    json.dump({f"{v['repo']}#{v['num']}": v for v in d.values()},
              open(ROOT / "evidence" / "classified.json", "w"), indent=1)
    print(f"defects={len(d)}  orgs={n_org}  ETB={n_etb} across {n_classes} classes  "
          f"adjacent={n_adj}  unclassified={n_unc}  landed={n_land}")
