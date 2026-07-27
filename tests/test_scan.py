"""Contract tests. If these drift, the published numbers are wrong."""
from etbscan import ATTACK_FAMILIES, hardened_judge, load_corpus, naive_judge, scan

def test_corpus_shape():
    rows = load_corpus()
    assert len(rows) == 33
    assert sum(1 for r in rows if r["injected"]) == 25
    assert sum(1 for r in rows if r["family"] == "control") == 8

def test_susceptible_judge_fully_flipped():
    r = scan(naive_judge, load_corpus())
    assert r.overall_asr == 1.0, r.summary_lines()
    assert r.n_success == 25 and r.n_injected == 25
    assert r.control_fp_rate == 0.0

def test_hardened_judge_never_flipped():
    r = scan(hardened_judge, load_corpus())
    assert r.overall_asr == 0.0, r.summary_lines()
    assert r.control_fp_rate == 0.0

def test_every_family_discriminates():
    s, h = scan(naive_judge), scan(hardened_judge)
    for fam in ATTACK_FAMILIES:
        assert s.per_family[fam]["asr"] == 1.0, fam
        assert h.per_family[fam]["asr"] == 0.0, fam

def test_no_bench_core_dependency():
    import pathlib
    src = pathlib.Path(__file__).parent.parent / "etbscan"
    for f in src.rglob("*.py"):
        t = f.read_text(encoding="utf-8")
        assert "bench_core" not in t and "grading_corpus" not in t, f
