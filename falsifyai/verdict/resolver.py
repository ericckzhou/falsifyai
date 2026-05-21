"""Placeholder verdict resolver.

This module is intentionally minimal. It exists so ``falsifyai run`` has
*something* to call between "invariants ran" and "save the artifact" in
PR #8. The full resolver — with stratified bootstrap CI, ConsistencyOracle
integration, and CONSISTENTLY_WRONG detection — lands in Week 2.

Placeholder semantics (per PR #8 plan, open-question 11b):

- No perturbed runs at all OR no invariant results across them -> INSUFFICIENT
- Any invariant on any perturbed run failed -> FRAGILE
- All invariants on all perturbed runs passed -> STABLE
- Confidence is the fraction of passing invariant results across all
  perturbed runs in the case.

The placeholder NEVER returns CONSISTENTLY_WRONG (no ConsistencyOracle yet)
or INVALID_EVAL (no meta-oracle yet). Both verdicts are still valid inputs
to ``resolve_session`` — callers may supply them on cases that already had
those verdicts assigned by a future resolver path.
"""

# TODO(week-2): replace with full bootstrap-CI + ConsistencyOracle resolver.

from falsifyai.replay.models import CaseResult, PerturbedRun, SessionVerdict
from falsifyai.verdict.models import Verdict


def resolve_case(perturbed_runs: list[PerturbedRun]) -> tuple[Verdict, float]:
    """Decide a case-level verdict + confidence from its perturbed runs.

    Returns ``(verdict, confidence)`` where confidence is in ``[0, 1]``.
    """
    if not perturbed_runs:
        return Verdict.INSUFFICIENT, 0.0

    all_results = [r for run in perturbed_runs for r in run.invariant_results]
    if not all_results:
        return Verdict.INSUFFICIENT, 0.0

    passed = sum(1 for r in all_results if r.passed)
    total = len(all_results)
    confidence = passed / total

    if passed < total:
        return Verdict.FRAGILE, confidence
    return Verdict.STABLE, confidence


def resolve_session(case_results: list[CaseResult]) -> SessionVerdict:
    """Roll case-level verdicts up into a session-level verdict.

    Priority (worst-first):
    1. Any CONSISTENTLY_WRONG -> CONSISTENTLY_WRONG
    2. Any FRAGILE -> FRAGILE
    3. All INSUFFICIENT -> INSUFFICIENT
    4. Otherwise -> STABLE

    Confidence is the mean of per-case confidences (or 0.0 for empty input).
    """
    fragile_count = sum(1 for c in case_results if c.verdict is Verdict.FRAGILE)
    consistently_wrong_count = sum(
        1 for c in case_results if c.verdict is Verdict.CONSISTENTLY_WRONG
    )
    case_count = len(case_results)

    if case_count == 0:
        verdict = Verdict.INSUFFICIENT
        confidence = 0.0
    else:
        if consistently_wrong_count > 0:
            verdict = Verdict.CONSISTENTLY_WRONG
        elif fragile_count > 0:
            verdict = Verdict.FRAGILE
        elif all(c.verdict is Verdict.INSUFFICIENT for c in case_results):
            verdict = Verdict.INSUFFICIENT
        else:
            verdict = Verdict.STABLE
        confidence = sum(c.verdict_confidence for c in case_results) / case_count

    return SessionVerdict(
        session_verdict=verdict,
        confidence=confidence,
        case_count=case_count,
        fragile_count=fragile_count,
        consistently_wrong_count=consistently_wrong_count,
    )
