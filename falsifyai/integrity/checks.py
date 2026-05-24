"""Pure integrity checks over a stored ReplayArtifact (PR-31).

Eight checks, all required, all surface in the report. None re-resolve the
verdict; ``case.verdict`` is read from the artifact, never recomputed.

Discipline:
- No IO. Caller loads the artifact; checks operate on the in-memory value.
- No imports from ``falsifyai.verdict.resolver``. Enforced by
  ``tests/unit/test_verify_does_not_import_resolver.py``.
- Pre-PR-11 artifacts (CI fields all zero) pass check 7 trivially — that's
  correct: the zero sentinel is legitimate evidence "no CI was computed."

Public surface:
- :class:`CheckStatus` — PASS / FAIL enum
- :class:`CheckResult` — one per check
- :class:`IntegrityReport` — aggregate over all 8
- :func:`run_integrity_checks` — entry point
"""

import uuid
from dataclasses import dataclass
from enum import Enum

from falsifyai.replay.models import CaseResult, ReplayArtifact
from falsifyai.spec.materializer import compute_materialized_hash
from falsifyai.verdict.models import Verdict


class CheckStatus(Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    detail: str


@dataclass(frozen=True)
class IntegrityReport:
    session_id: str
    results: list[CheckResult]

    @property
    def all_passed(self) -> bool:
        return all(r.status is CheckStatus.PASS for r in self.results)


# ---------------------------------------------------------------------------
# Individual checks. Order is part of the public contract (rendering depends
# on stable ordering for predictable output).
# ---------------------------------------------------------------------------


def _check_session_id_format(artifact: ReplayArtifact) -> CheckResult:
    """Check 1: session_id parses as a UUID.

    Accepts both 32-char hex (``uuid.uuid4().hex``, the production form) and
    8-4-4-4-12 hyphenated form (used in some fixtures and test data).
    """
    try:
        uuid.UUID(artifact.session_id)
    except (ValueError, AttributeError, TypeError):
        return CheckResult(
            name="session_id_format",
            status=CheckStatus.FAIL,
            detail=f"session_id {artifact.session_id!r} is not a parseable UUID",
        )
    return CheckResult(
        name="session_id_format",
        status=CheckStatus.PASS,
        detail=f"session_id {artifact.session_id!r} is a valid UUID",
    )


def _check_created_at_tz_aware(artifact: ReplayArtifact) -> CheckResult:
    """Check 2: created_at is tz-aware.

    The serializer rejects naive datetimes at save time; this check catches
    in-place corruption (e.g., raw payload mutation, deserializer bug).
    """
    dt = artifact.created_at
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return CheckResult(
            name="created_at_tz_aware",
            status=CheckStatus.FAIL,
            detail=f"created_at {dt.isoformat()} is tz-naive; serializer should have rejected this",
        )
    return CheckResult(
        name="created_at_tz_aware",
        status=CheckStatus.PASS,
        detail=f"created_at {dt.isoformat()} is tz-aware",
    )


def _check_materialized_hash(artifact: ReplayArtifact) -> CheckResult:
    """Check 3 (load-bearing): recompute materialized_hash and compare to stored.

    Uses the exact same ``compute_materialized_hash`` function as
    ``materialize()`` — no re-implementation. If the two diverge, the artifact's
    preserved evidence has been tampered with at the perturbation-text or
    lineage level.
    """
    expected = compute_materialized_hash(artifact.materialized.cases)
    stored = artifact.materialized_hash
    if expected != stored:
        return CheckResult(
            name="materialized_hash",
            status=CheckStatus.FAIL,
            detail=f"expected {expected[:12]}... ; stored {stored[:12]}... (mismatch)",
        )
    return CheckResult(
        name="materialized_hash",
        status=CheckStatus.PASS,
        detail=f"recomputed hash {expected[:12]}... matches stored",
    )


def _check_case_count_consistency(artifact: ReplayArtifact) -> CheckResult:
    """Check 4: session_verdict.case_count == len(case_results)."""
    expected = len(artifact.case_results)
    stored = artifact.session_verdict.case_count
    if expected != stored:
        return CheckResult(
            name="case_count_consistency",
            status=CheckStatus.FAIL,
            detail=f"session_verdict.case_count={stored} but len(case_results)={expected}",
        )
    return CheckResult(
        name="case_count_consistency",
        status=CheckStatus.PASS,
        detail=f"session_verdict.case_count={stored} matches case_results length",
    )


def _count_verdict(cases: list[CaseResult], verdict: Verdict) -> int:
    return sum(1 for c in cases if c.verdict is verdict)


def _check_fragile_count_consistency(artifact: ReplayArtifact) -> CheckResult:
    """Check 5: session_verdict.fragile_count == count of per-case FRAGILE verdicts."""
    expected = _count_verdict(artifact.case_results, Verdict.FRAGILE)
    stored = artifact.session_verdict.fragile_count
    if expected != stored:
        return CheckResult(
            name="fragile_count_consistency",
            status=CheckStatus.FAIL,
            detail=f"session_verdict.fragile_count={stored} but per-case FRAGILE count={expected}",
        )
    return CheckResult(
        name="fragile_count_consistency",
        status=CheckStatus.PASS,
        detail=f"session_verdict.fragile_count={stored} matches per-case count",
    )


def _check_consistently_wrong_count_consistency(artifact: ReplayArtifact) -> CheckResult:
    """Check 6: session_verdict.consistently_wrong_count matches per-case CW count."""
    expected = _count_verdict(artifact.case_results, Verdict.CONSISTENTLY_WRONG)
    stored = artifact.session_verdict.consistently_wrong_count
    if expected != stored:
        return CheckResult(
            name="consistently_wrong_count_consistency",
            status=CheckStatus.FAIL,
            detail=(
                f"session_verdict.consistently_wrong_count={stored} "
                f"but per-case CONSISTENTLY_WRONG count={expected}"
            ),
        )
    return CheckResult(
        name="consistently_wrong_count_consistency",
        status=CheckStatus.PASS,
        detail=f"session_verdict.consistently_wrong_count={stored} matches per-case count",
    )


def _check_ci_bounds(artifact: ReplayArtifact) -> CheckResult:
    """Check 7: per case, 0 ≤ stability_ci_low ≤ stability ≤ stability_ci_high ≤ 1.

    Pre-PR-11 artifacts (all-zero CI fields) pass trivially — the ordering
    holds and the values are within bounds. That's correct: the zero sentinel
    is legitimate evidence "no CI was computed at run time."
    """
    violations: list[str] = []
    for c in artifact.case_results:
        lo, mid, hi = c.stability_ci_low, c.stability, c.stability_ci_high
        if not (0.0 <= lo <= mid <= hi <= 1.0):
            violations.append(
                f"case {c.case_id!r}: ci_low={lo} stability={mid} ci_high={hi} "
                "violates 0 ≤ ci_low ≤ stability ≤ ci_high ≤ 1"
            )
    if violations:
        return CheckResult(
            name="ci_bounds",
            status=CheckStatus.FAIL,
            detail="; ".join(violations),
        )
    return CheckResult(
        name="ci_bounds",
        status=CheckStatus.PASS,
        detail=f"all {len(artifact.case_results)} case(s) have valid CI bounds",
    )


def _check_falsifiability_score_range(artifact: ReplayArtifact) -> CheckResult:
    """Check 8: 0 ≤ session_verdict.falsifyai_falsifiability_score ≤ 1."""
    score = artifact.session_verdict.falsifyai_falsifiability_score
    if not (0.0 <= score <= 1.0):
        return CheckResult(
            name="falsifiability_score_range",
            status=CheckStatus.FAIL,
            detail=f"falsifyai_falsifiability_score={score} is outside [0, 1]",
        )
    return CheckResult(
        name="falsifiability_score_range",
        status=CheckStatus.PASS,
        detail=f"falsifyai_falsifiability_score={score:.2f} is in [0, 1]",
    )


_CHECKS = [
    _check_session_id_format,
    _check_created_at_tz_aware,
    _check_materialized_hash,
    _check_case_count_consistency,
    _check_fragile_count_consistency,
    _check_consistently_wrong_count_consistency,
    _check_ci_bounds,
    _check_falsifiability_score_range,
]


def run_integrity_checks(artifact: ReplayArtifact) -> IntegrityReport:
    """Run all 8 integrity checks against the artifact and return an aggregated report."""
    results = [check(artifact) for check in _CHECKS]
    return IntegrityReport(session_id=artifact.session_id, results=results)
