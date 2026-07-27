"""The plugin's own contract: it must pass a hardened judge and fail a naive one."""
import pytest
from etbscan import hardened_judge, naive_judge


def test_hardened_judge_passes(etb_scan):
    r = etb_scan(hardened_judge)
    assert r.overall_asr == 0.0


def test_naive_judge_is_caught(etb_scan):
    with pytest.raises(pytest.fail.Exception):
        etb_scan(naive_judge)


def test_naive_judge_allowed_under_explicit_ceiling(etb_scan):
    r = etb_scan(naive_judge, max_asr=1.0)
    assert r.overall_asr == 1.0


def test_result_fixture_does_not_assert(etb_scan_result):
    r = etb_scan_result(naive_judge)
    assert r.overall_asr == 1.0 and r.control_fp_rate == 0.0
