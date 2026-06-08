"""Unit tests for ``falsifyai.integrity.checks`` (PR-31).

Exercises CheckResult, CheckStatus, IntegrityReport, and run_integrity_checks.

Eight integrity checks per PR-31 plan §3:

1. session_id_format — parseable as a UUID
2. created_at_tz_aware — datetime is tz-aware (not naive)
3. materialized_hash — recompute from ``MaterializedSpec.cases`` matches stored
4. case_count_consistency — session_verdict.case_count == len(case_results)
5. fragile_count_consistency — session_verdict.fragile_count == count(FRAGILE)
6. consistently_wrong_count_consistency — session_verdict.consistently_wrong_count == count(CW)
7. ci_bounds — for each case: 0 ≤ ci_low ≤ stability ≤ ci_high ≤ 1
8. falsifiability_score_range — 0 ≤ session_verdict.falsifyai_falsifiability_score ≤ 1
"""

import dataclasses
from datetime import UTC, datetime

from falsifyai.integrity.checks import (
    CheckResult,
    CheckStatus,
    IntegrityReport,
    run_integrity_checks,
)
from falsifyai.spec.materializer import compute_materialized_hash
from falsifyai.verdict.models import Verdict
from tests.fixtures.build_artifact import make_artifact

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_artifact(**kwargs):
    """Build a fixture artifact with the **correct** materialized_hash.

    ``make_artifact()`` uses a placeholder hash ("b"*64). The materialized-hash
    check requires the stored value to equal ``compute_materialized_hash(cases)``.
    This helper recomputes and patches both the top-level field and the nested
    ``MaterializedSpec.materialized_hash`` so the clean baseline passes check 3.
    """
    a = make_artifact(**kwargs)
    correct = compute_materialized_hash(a.materialized.cases)
    return dataclasses.replace(
        a,
        materialized_hash=correct,
        materialized=dataclasses.replace(a.materialized, materialized_hash=correct),
    )


def _by_name(report: IntegrityReport, name: str) -> CheckResult:
    for r in report.results:
        if r.name == name:
            return r
    raise AssertionError(
        f"No check named {name!r} in report. Got: {[r.name for r in report.results]}"
    )


# ---------------------------------------------------------------------------
# Top-level API surface
# ---------------------------------------------------------------------------


def test_check_status_is_enum_with_pass_fail() -> None:
    assert CheckStatus.PASS.value == "pass"
    assert CheckStatus.FAIL.value == "fail"


def test_check_result_carries_name_status_detail() -> None:
    r = CheckResult(name="session_id_format", status=CheckStatus.PASS, detail="valid uuid")
    assert r.name == "session_id_format"
    assert r.status is CheckStatus.PASS
    assert r.detail == "valid uuid"


def test_integrity_report_all_passed_true_on_clean() -> None:
    a = _clean_artifact()
    report = run_integrity_checks(a)
    assert report.all_passed is True
    assert report.session_id == a.session_id
    assert len(report.results) == 8
    assert all(r.status is CheckStatus.PASS for r in report.results)


def test_integrity_report_all_passed_false_when_any_fails() -> None:
    a = _clean_artifact()
    bad = dataclasses.replace(a, materialized_hash="0" * 64)
    report = run_integrity_checks(bad)
    assert report.all_passed is False


def test_integrity_report_results_ordered_stable() -> None:
    """Order of results matters for predictable rendering; assert it's stable."""
    a = _clean_artifact()
    report = run_integrity_checks(a)
    names = [r.name for r in report.results]
    assert names == [
        "session_id_format",
        "created_at_tz_aware",
        "materialized_hash",
        "case_count_consistency",
        "fragile_count_consistency",
        "consistently_wrong_count_consistency",
        "ci_bounds",
        "falsifiability_score_range",
    ]


# ---------------------------------------------------------------------------
# Check 1: session_id format
# ---------------------------------------------------------------------------


def test_check_1_session_id_passes_on_uuid_hex_32() -> None:
    a = _clean_artifact(session_id="7e51299481d5420d9181e71ba0449348")
    r = _by_name(run_integrity_checks(a), "session_id_format")
    assert r.status is CheckStatus.PASS


def test_check_1_session_id_passes_on_uuid_hyphenated() -> None:
    a = _clean_artifact(session_id="11111111-1111-1111-1111-111111111111")
    r = _by_name(run_integrity_checks(a), "session_id_format")
    assert r.status is CheckStatus.PASS


def test_check_1_session_id_fails_on_garbage() -> None:
    a = _clean_artifact(session_id="not-a-uuid")
    r = _by_name(run_integrity_checks(a), "session_id_format")
    assert r.status is CheckStatus.FAIL
    assert "not-a-uuid" in r.detail or "session_id" in r.detail.lower()


# ---------------------------------------------------------------------------
# Check 2: created_at timezone awareness
# ---------------------------------------------------------------------------


def test_check_2_created_at_passes_on_utc() -> None:
    a = _clean_artifact(created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=UTC))
    r = _by_name(run_integrity_checks(a), "created_at_tz_aware")
    assert r.status is CheckStatus.PASS


def test_check_2_created_at_fails_on_naive() -> None:
    """Verify catches in-place corruption — the serializer rejects naive at save time."""
    a = _clean_artifact()
    bad = dataclasses.replace(a, created_at=datetime(2026, 5, 21, 12, 0, 0))
    r = _by_name(run_integrity_checks(bad), "created_at_tz_aware")
    assert r.status is CheckStatus.FAIL


# ---------------------------------------------------------------------------
# Check 3: materialized_hash recomputation (load-bearing)
# ---------------------------------------------------------------------------


def test_check_3_materialized_hash_passes_on_correct() -> None:
    a = _clean_artifact()
    r = _by_name(run_integrity_checks(a), "materialized_hash")
    assert r.status is CheckStatus.PASS


def test_check_3_materialized_hash_fails_on_corrupted() -> None:
    a = _clean_artifact()
    bad = dataclasses.replace(a, materialized_hash="0" * 64)
    r = _by_name(run_integrity_checks(bad), "materialized_hash")
    assert r.status is CheckStatus.FAIL
    assert "expected" in r.detail.lower() or "mismatch" in r.detail.lower()


# ---------------------------------------------------------------------------
# Check 4: session_verdict.case_count
# ---------------------------------------------------------------------------


def test_check_4_case_count_passes_on_match() -> None:
    a = _clean_artifact()
    r = _by_name(run_integrity_checks(a), "case_count_consistency")
    assert r.status is CheckStatus.PASS


def test_check_4_case_count_fails_on_mismatch() -> None:
    a = _clean_artifact()
    bad = dataclasses.replace(
        a, session_verdict=dataclasses.replace(a.session_verdict, case_count=99)
    )
    r = _by_name(run_integrity_checks(bad), "case_count_consistency")
    assert r.status is CheckStatus.FAIL


# ---------------------------------------------------------------------------
# Check 5: fragile_count
# ---------------------------------------------------------------------------


def test_check_5_fragile_count_passes_on_correct() -> None:
    a = _clean_artifact(verdict=Verdict.FRAGILE)
    r = _by_name(run_integrity_checks(a), "fragile_count_consistency")
    assert r.status is CheckStatus.PASS


def test_check_5_fragile_count_fails_on_mismatch() -> None:
    a = _clean_artifact(verdict=Verdict.STABLE)
    bad = dataclasses.replace(
        a, session_verdict=dataclasses.replace(a.session_verdict, fragile_count=99)
    )
    r = _by_name(run_integrity_checks(bad), "fragile_count_consistency")
    assert r.status is CheckStatus.FAIL


# ---------------------------------------------------------------------------
# Check 6: consistently_wrong_count
# ---------------------------------------------------------------------------


def test_check_6_cw_count_passes_on_correct() -> None:
    a = _clean_artifact(verdict=Verdict.CONSISTENTLY_WRONG)
    r = _by_name(run_integrity_checks(a), "consistently_wrong_count_consistency")
    assert r.status is CheckStatus.PASS


def test_check_6_cw_count_fails_on_mismatch() -> None:
    a = _clean_artifact(verdict=Verdict.STABLE)
    bad = dataclasses.replace(
        a, session_verdict=dataclasses.replace(a.session_verdict, consistently_wrong_count=99)
    )
    r = _by_name(run_integrity_checks(bad), "consistently_wrong_count_consistency")
    assert r.status is CheckStatus.FAIL


# ---------------------------------------------------------------------------
# Check 7: per-case CI bounds 0 ≤ ci_low ≤ stability ≤ ci_high ≤ 1
# ---------------------------------------------------------------------------


def test_check_7_ci_bounds_passes_on_valid_fixture() -> None:
    a = _clean_artifact()  # 0.88 / 0.92 / 0.96 by default
    r = _by_name(run_integrity_checks(a), "ci_bounds")
    assert r.status is CheckStatus.PASS


def test_check_7_ci_bounds_passes_on_pre_pr11_zeros() -> None:
    """Pre-PR-11 artifacts had zero CI fields. 0 ≤ 0 ≤ 0 ≤ 1 holds trivially."""
    a = _clean_artifact()
    case = a.case_results[0]
    zeroed = dataclasses.replace(case, stability=0.0, stability_ci_low=0.0, stability_ci_high=0.0)
    aged = dataclasses.replace(a, case_results=[zeroed])
    r = _by_name(run_integrity_checks(aged), "ci_bounds")
    assert r.status is CheckStatus.PASS


def test_check_7_ci_bounds_fails_when_ci_low_above_stability() -> None:
    a = _clean_artifact()
    case = a.case_results[0]
    bad_case = dataclasses.replace(case, stability_ci_low=0.99, stability=0.5)
    bad = dataclasses.replace(a, case_results=[bad_case])
    r = _by_name(run_integrity_checks(bad), "ci_bounds")
    assert r.status is CheckStatus.FAIL


def test_check_7_ci_bounds_fails_when_ci_high_above_one() -> None:
    a = _clean_artifact()
    case = a.case_results[0]
    bad_case = dataclasses.replace(case, stability_ci_high=1.5)
    bad = dataclasses.replace(a, case_results=[bad_case])
    r = _by_name(run_integrity_checks(bad), "ci_bounds")
    assert r.status is CheckStatus.FAIL


def test_check_7_ci_bounds_fails_on_negative_ci_low() -> None:
    a = _clean_artifact()
    case = a.case_results[0]
    bad_case = dataclasses.replace(case, stability_ci_low=-0.1)
    bad = dataclasses.replace(a, case_results=[bad_case])
    r = _by_name(run_integrity_checks(bad), "ci_bounds")
    assert r.status is CheckStatus.FAIL


# ---------------------------------------------------------------------------
# Check 8: falsifiability score in [0, 1]
# ---------------------------------------------------------------------------


def test_check_8_falsifiability_passes_on_valid() -> None:
    a = _clean_artifact()
    r = _by_name(run_integrity_checks(a), "falsifiability_score_range")
    assert r.status is CheckStatus.PASS


def test_check_8_falsifiability_passes_at_zero_lower_bound() -> None:
    a = _clean_artifact()
    sv = dataclasses.replace(a.session_verdict, falsifyai_falsifiability_score=0.0)
    a2 = dataclasses.replace(a, session_verdict=sv)
    r = _by_name(run_integrity_checks(a2), "falsifiability_score_range")
    assert r.status is CheckStatus.PASS


def test_check_8_falsifiability_passes_at_one_upper_bound() -> None:
    a = _clean_artifact()
    sv = dataclasses.replace(a.session_verdict, falsifyai_falsifiability_score=1.0)
    a2 = dataclasses.replace(a, session_verdict=sv)
    r = _by_name(run_integrity_checks(a2), "falsifiability_score_range")
    assert r.status is CheckStatus.PASS


def test_check_8_falsifiability_fails_above_one() -> None:
    a = _clean_artifact()
    sv = dataclasses.replace(a.session_verdict, falsifyai_falsifiability_score=1.1)
    a2 = dataclasses.replace(a, session_verdict=sv)
    r = _by_name(run_integrity_checks(a2), "falsifiability_score_range")
    assert r.status is CheckStatus.FAIL


def test_check_8_falsifiability_fails_negative() -> None:
    a = _clean_artifact()
    sv = dataclasses.replace(a.session_verdict, falsifyai_falsifiability_score=-0.01)
    a2 = dataclasses.replace(a, session_verdict=sv)
    r = _by_name(run_integrity_checks(a2), "falsifiability_score_range")
    assert r.status is CheckStatus.FAIL
