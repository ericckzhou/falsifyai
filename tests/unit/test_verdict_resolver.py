"""Tests for falsifyai.verdict.resolver — placeholder verdict resolution.

Per the PR #8 plan (decision B2 + open-question 11b): the resolver shipped
here is a deliberate placeholder. It exists so ``falsifyai run`` has
*something* to call between "invariants ran" and "save the artifact." The
real resolver with bootstrap-CI + ConsistencyOracle lands in Week 2.

Placeholder semantics:
- No perturbed runs at all → INSUFFICIENT.
- Any invariant on any perturbed run failed → FRAGILE.
- All invariants on all perturbed runs passed → STABLE.
- Confidence: fraction of passing invariant results across all perturbed runs.
"""

import pytest

from falsifyai.execution.models import Execution, ModelRequest
from falsifyai.invariants.base import InvariantResult, Severity
from falsifyai.perturbation.base import (
    PerturbationCategory,
    PerturbationLineage,
    PerturbedInput,
    hash_input,
)
from falsifyai.replay.models import CaseResult, PerturbedRun
from falsifyai.verdict.models import Verdict
from falsifyai.verdict.resolver import resolve_case, resolve_session


def _execution(prompt: str = "ping", output: str = "pong") -> Execution:
    req = ModelRequest(
        provider="mock",
        model="mock-model",
        prompt=prompt,
        temperature=0.0,
        max_tokens=128,
        seed=42,
        timeout_seconds=30,
    )
    return Execution(
        request=req,
        output_text=output,
        latency_ms=1.0,
        prompt_tokens=1,
        completion_tokens=1,
        cached=False,
        seed_provided=True,
    )


def _perturbed_input(text: str = "p1ng") -> PerturbedInput:
    return PerturbedInput(
        text=text,
        lineage=PerturbationLineage(
            perturbation_type="typo_noise",
            category=PerturbationCategory.LEXICAL,
            method="substitute",
            seed=1,
            params={"sample_index": 0},
            parent_input_hash=hash_input("ping"),
        ),
        validity_score=1.0,
    )


def _invariant_result(passed: bool, name: str = "contains") -> InvariantResult:
    return InvariantResult(
        invariant_name=name,
        passed=passed,
        score=1.0 if passed else 0.0,
        details="" if passed else "missing values",
        severity=Severity.HIGH,
        evidence={},
    )


def _perturbed_run(*invariant_passes: bool) -> PerturbedRun:
    return PerturbedRun(
        perturbed_input=_perturbed_input(),
        execution=_execution(),
        invariant_results=[_invariant_result(passed) for passed in invariant_passes],
    )


def _case_result(verdict: Verdict, confidence: float = 0.9) -> CaseResult:
    return CaseResult(
        case_id="c",
        original_input="ping",
        original_execution=_execution(),
        perturbed=[],
        verdict=verdict,
        verdict_confidence=confidence,
    )


# ---------------------------------------------------------------------------
# resolve_case
# ---------------------------------------------------------------------------


def test_case_with_no_perturbed_runs_is_insufficient() -> None:
    verdict, confidence = resolve_case([])
    assert verdict is Verdict.INSUFFICIENT
    assert confidence == 0.0


def test_case_with_all_invariants_passing_is_stable() -> None:
    runs = [_perturbed_run(True, True), _perturbed_run(True, True)]
    verdict, confidence = resolve_case(runs)
    assert verdict is Verdict.STABLE
    assert confidence == pytest.approx(1.0)


def test_case_with_any_invariant_failure_is_fragile() -> None:
    """Per open-question 11b: any invariant fail on any perturbed run → FRAGILE."""
    runs = [_perturbed_run(True, True), _perturbed_run(True, False)]
    verdict, confidence = resolve_case(runs)
    assert verdict is Verdict.FRAGILE
    # 3 of 4 invariant results passed.
    assert confidence == pytest.approx(0.75)


def test_confidence_is_fraction_of_passing_invariants() -> None:
    # 2 perturbed runs × 2 invariants each = 4 results; 1 fails -> 0.75
    runs = [_perturbed_run(True, True), _perturbed_run(False, True)]
    _, confidence = resolve_case(runs)
    assert confidence == pytest.approx(0.75)


def test_case_with_perturbed_runs_but_no_invariants_is_insufficient() -> None:
    """A spec with no invariants configured produces no judgment material."""
    runs = [
        PerturbedRun(
            perturbed_input=_perturbed_input(),
            execution=_execution(),
            invariant_results=[],
        )
    ]
    verdict, confidence = resolve_case(runs)
    assert verdict is Verdict.INSUFFICIENT
    assert confidence == 0.0


# ---------------------------------------------------------------------------
# resolve_session
# ---------------------------------------------------------------------------


def test_session_with_all_stable_cases_is_stable() -> None:
    cases = [_case_result(Verdict.STABLE, 0.95), _case_result(Verdict.STABLE, 0.9)]
    sv = resolve_session(cases)
    assert sv.session_verdict is Verdict.STABLE
    assert sv.case_count == 2
    assert sv.fragile_count == 0
    assert sv.consistently_wrong_count == 0
    assert sv.confidence == pytest.approx(0.925)


def test_session_with_any_fragile_case_is_fragile() -> None:
    cases = [
        _case_result(Verdict.STABLE, 1.0),
        _case_result(Verdict.FRAGILE, 0.5),
        _case_result(Verdict.STABLE, 0.9),
    ]
    sv = resolve_session(cases)
    assert sv.session_verdict is Verdict.FRAGILE
    assert sv.fragile_count == 1
    assert sv.case_count == 3


def test_session_with_all_insufficient_is_insufficient() -> None:
    cases = [_case_result(Verdict.INSUFFICIENT, 0.0), _case_result(Verdict.INSUFFICIENT, 0.0)]
    sv = resolve_session(cases)
    assert sv.session_verdict is Verdict.INSUFFICIENT
    assert sv.case_count == 2


def test_session_with_consistently_wrong_takes_priority() -> None:
    """CONSISTENTLY_WRONG wins over FRAGILE per plan section 2.2 severity ordering."""
    cases = [
        _case_result(Verdict.FRAGILE, 0.5),
        _case_result(Verdict.CONSISTENTLY_WRONG, 0.9),
    ]
    sv = resolve_session(cases)
    assert sv.session_verdict is Verdict.CONSISTENTLY_WRONG
    assert sv.fragile_count == 1
    assert sv.consistently_wrong_count == 1


def test_empty_session_is_insufficient() -> None:
    sv = resolve_session([])
    assert sv.session_verdict is Verdict.INSUFFICIENT
    assert sv.case_count == 0
    assert sv.fragile_count == 0
    assert sv.consistently_wrong_count == 0
