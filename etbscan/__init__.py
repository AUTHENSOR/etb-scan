"""etb-scan: measure a judge's Evaluator Trust Boundary susceptibility (ETB-01).

Offline, stdlib-only, zero model spend.
"""
from etbscan.loader import load_judge
from etbscan.judges import hardened_judge, is_pass, naive_judge, sanitize_candidate
from etbscan.scan import (
    ATTACK_FAMILIES,
    CONTROL_FAMILY,
    ScanResult,
    ScenarioResult,
    load_corpus,
    scan,
)

__all__ = [
    "scan", "load_corpus", "ScanResult", "ScenarioResult",
    "naive_judge", "hardened_judge", "is_pass", "sanitize_candidate",
    "ATTACK_FAMILIES", "CONTROL_FAMILY", "load_judge",
]
__version__ = "0.1.0"
