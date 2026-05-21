"""Tests for falsifyai.verdict.resolver.

Rewrites the PR #8 placeholder tests against the real (PR #11) resolver
that does stratified bootstrap CI, lightweight CONSISTENTLY_WRONG, and
worst-case stratum surfacing.

Verdict priority: INSUFFICIENT -> CONSISTENTLY_WRONG -> FRAGILE -> STABLE.
"""

import pytest

from falsifyai.execution.models import Execution, ModelRequest
from falsifyai.invariants.base import InvariantResult, Severity
from falsifyai.invariants.contains import ContainsInvariant
from falsifyai.perturbation.base import (
    PerturbationCategory,
    PerturbationLineage,
    PerturbedInput,
)
from falsifyai.replay.models import PerturbedRun
from falsifyai.spec.models import ExpectedSection
from falsifyai.verdict.models import Verdict
from falsifyai.verdict.resolver import resolve_case, resolve_session

CASE_SEED = 4242


def _exec(prompt: str, output: str) -> Execution:
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


def _perturbed_run(family: str, prompt: str, output: str, *invariant_passes: bool) -> PerturbedRun:
    return PerturbedRun(
        perturbed_input=PerturbedInput(
            text=prompt,
            lineage=PerturbationLineage(
                perturbation_type=family,
                category=PerturbationCategory.LEXICAL,
                method="m",
                seed=1,
                params={"sample_index": 0},
                parent_input_hash="h",
            ),
            validity_score=1.0,
        ),
        execution=_exec(prompt, output),
        invariant_results=[
            InvariantResult(
                invariant_name=f"inv_{i}",
                passed=passed,
                score=1.0 if passed else 0.0,
                details="",
                severity=Severity.HIGH,
                evidence={},
            )
            for i, passed in enumerate(invariant_passes)
        ],
    )


def _case_result(verdict: Verdict, confidence: float = 0.9):
    """Helper: build a CaseResult fixture for resolve_session tests."""
    from falsifyai.replay.models import CaseResult

    return CaseResult(
        case_id="c",
        original_input="ping",
        original_execution=_exec("ping", "pong"),
        perturbed=[],
        verdict=verdict,
        verdict_confidence=confidence,
        stability=confidence,
        stability_ci_low=confidence,
        stability_ci_high=confidence,
    )


# ---------------------------------------------------------------------------
# resolve_case -- INSUFFICIENT
# ---------------------------------------------------------------------------


def test_no_perturbed_runs_is_insufficient() -> None:
    result = resolve_case(
        case_id="c",
        original_input="What is the capital of France?",
        original_execution=_exec("What is the capital of France?", "Paris."),
        perturbed_runs=[],
        expected=ExpectedSection(contains=["Paris"]),
        invariants=[ContainsInvariant(values=["Paris"], severity=Severity.HIGH)],
        stable_threshold=0.95,
        case_seed=CASE_SEED,
    )
    assert result.verdict is Verdict.INSUFFICIENT
    assert result.stability == 0.0


def test_perturbed_runs_with_no_invariants_is_insufficient() -> None:
    """A spec with perturbations but no invariants produces no judgment material."""
    run = PerturbedRun(
        perturbed_input=PerturbedInput(
            text="x",
            lineage=PerturbationLineage(
                perturbation_type="typo_noise",
                category=PerturbationCategory.LEXICAL,
                method="m",
                seed=1,
                params={"sample_index": 0},
                parent_input_hash="h",
            ),
            validity_score=1.0,
        ),
        execution=_exec("x", "y"),
        invariant_results=[],
    )
    result = resolve_case(
        case_id="c",
        original_input="orig",
        original_execution=_exec("orig", "out"),
        perturbed_runs=[run],
        expected=ExpectedSection(),
        invariants=[],
        stable_threshold=0.95,
        case_seed=CASE_SEED,
    )
    assert result.verdict is Verdict.INSUFFICIENT


# ---------------------------------------------------------------------------
# resolve_case -- CONSISTENTLY_WRONG priority over FRAGILE
# ---------------------------------------------------------------------------


def test_consistently_wrong_takes_priority_over_fragile() -> None:
    """Original wrong + all perturbed wrong + invariants fail -> CONSISTENTLY_WRONG."""
    perturbed = [
        _perturbed_run("typo_noise", "p1", "London.", False),
        _perturbed_run("casing_variant", "p2", "London.", False),
    ]
    result = resolve_case(
        case_id="c",
        original_input="What is the capital of France?",
        original_execution=_exec("What is the capital of France?", "London is the capital."),
        perturbed_runs=perturbed,
        expected=ExpectedSection(contains=["Paris"]),
        invariants=[ContainsInvariant(values=["Paris"], severity=Severity.HIGH)],
        stable_threshold=0.95,
        case_seed=CASE_SEED,
    )
    assert result.verdict is Verdict.CONSISTENTLY_WRONG


def test_original_correct_perturbed_wrong_is_fragile_not_consistently_wrong() -> None:
    perturbed = [
        _perturbed_run("typo_noise", "p1", "London.", False),
        _perturbed_run("typo_noise", "p2", "London.", False),
    ]
    result = resolve_case(
        case_id="c",
        original_input="What is the capital of France?",
        original_execution=_exec("...", "Paris is the capital."),  # correct
        perturbed_runs=perturbed,
        expected=ExpectedSection(contains=["Paris"]),
        invariants=[ContainsInvariant(values=["Paris"], severity=Severity.HIGH)],
        stable_threshold=0.95,
        case_seed=CASE_SEED,
    )
    assert result.verdict is Verdict.FRAGILE


# ---------------------------------------------------------------------------
# resolve_case -- FRAGILE / STABLE based on CI lower bound
# ---------------------------------------------------------------------------


def test_all_invariants_pass_yields_stable_with_high_ci() -> None:
    perturbed = [
        _perturbed_run("typo_noise", "p1", "Paris.", True),
        _perturbed_run("typo_noise", "p2", "Paris.", True),
        _perturbed_run("casing_variant", "p3", "Paris.", True),
    ]
    result = resolve_case(
        case_id="c",
        original_input="...",
        original_execution=_exec("...", "Paris."),
        perturbed_runs=perturbed,
        expected=ExpectedSection(contains=["Paris"]),
        invariants=[ContainsInvariant(values=["Paris"], severity=Severity.HIGH)],
        stable_threshold=0.95,
        case_seed=CASE_SEED,
    )
    assert result.verdict is Verdict.STABLE
    assert result.stability == pytest.approx(1.0)
    assert result.stability_ci_low == pytest.approx(1.0)


def test_one_family_drops_to_fragile_via_worst_case_stratification() -> None:
    """typo_noise all pass; casing_variant all fail. Worst-case wins -> FRAGILE."""
    perturbed = [
        _perturbed_run("typo_noise", "p1", "Paris.", True),
        _perturbed_run("typo_noise", "p2", "Paris.", True),
        _perturbed_run("typo_noise", "p3", "Paris.", True),
        _perturbed_run("casing_variant", "p4", "London.", False),
        _perturbed_run("casing_variant", "p5", "London.", False),
    ]
    result = resolve_case(
        case_id="c",
        original_input="...",
        original_execution=_exec("...", "Paris."),
        perturbed_runs=perturbed,
        expected=ExpectedSection(contains=["Paris"]),
        invariants=[ContainsInvariant(values=["Paris"], severity=Severity.HIGH)],
        stable_threshold=0.95,
        case_seed=CASE_SEED,
    )
    assert result.verdict is Verdict.FRAGILE
    assert result.worst_case_family == "casing_variant"
    # Worst-case CI low is 0.0 (all-fail family); typo data does NOT drown it.
    assert result.stability_ci_low == pytest.approx(0.0)
    # Per-family preserves both families' point estimates.
    assert result.per_family_stability["typo_noise"] == pytest.approx(1.0)
    assert result.per_family_stability["casing_variant"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# resolve_case -- verdict_confidence == stability_ci_low (semantic continuity)
# ---------------------------------------------------------------------------


def test_verdict_confidence_equals_stability_ci_low() -> None:
    perturbed = [
        _perturbed_run("typo_noise", "p1", "Paris.", True),
        _perturbed_run("typo_noise", "p2", "Paris.", True),
    ]
    result = resolve_case(
        case_id="c",
        original_input="...",
        original_execution=_exec("...", "Paris."),
        perturbed_runs=perturbed,
        expected=ExpectedSection(contains=["Paris"]),
        invariants=[ContainsInvariant(values=["Paris"], severity=Severity.HIGH)],
        stable_threshold=0.95,
        case_seed=CASE_SEED,
    )
    assert result.verdict_confidence == result.stability_ci_low


# ---------------------------------------------------------------------------
# resolve_case -- bootstrap determinism
# ---------------------------------------------------------------------------


def test_bootstrap_is_deterministic_across_runs() -> None:
    perturbed = [
        _perturbed_run("typo_noise", "p1", "Paris.", True),
        _perturbed_run("typo_noise", "p2", "Paris.", False),
        _perturbed_run("typo_noise", "p3", "Paris.", True),
    ]
    kwargs = dict(
        case_id="c",
        original_input="...",
        original_execution=_exec("...", "Paris."),
        perturbed_runs=perturbed,
        expected=ExpectedSection(contains=["Paris"]),
        invariants=[ContainsInvariant(values=["Paris"], severity=Severity.HIGH)],
        stable_threshold=0.95,
        case_seed=CASE_SEED,
    )
    a = resolve_case(**kwargs)
    b = resolve_case(**kwargs)
    assert a.stability == b.stability
    assert a.stability_ci_low == b.stability_ci_low
    assert a.stability_ci_high == b.stability_ci_high


# ---------------------------------------------------------------------------
# resolve_session -- roll-up
# ---------------------------------------------------------------------------


def test_session_all_stable_is_stable() -> None:
    cases = [_case_result(Verdict.STABLE, 0.95), _case_result(Verdict.STABLE, 0.9)]
    sv = resolve_session(cases, falsifiability_score=0.7)
    assert sv.session_verdict is Verdict.STABLE
    assert sv.case_count == 2
    assert sv.falsifyai_falsifiability_score == pytest.approx(0.7)


def test_session_any_fragile_is_fragile() -> None:
    cases = [
        _case_result(Verdict.STABLE, 0.95),
        _case_result(Verdict.FRAGILE, 0.4),
    ]
    sv = resolve_session(cases, falsifiability_score=0.7)
    assert sv.session_verdict is Verdict.FRAGILE
    assert sv.fragile_count == 1


def test_session_consistently_wrong_takes_priority() -> None:
    cases = [
        _case_result(Verdict.FRAGILE, 0.4),
        _case_result(Verdict.CONSISTENTLY_WRONG, 0.9),
    ]
    sv = resolve_session(cases, falsifiability_score=0.7)
    assert sv.session_verdict is Verdict.CONSISTENTLY_WRONG
    assert sv.consistently_wrong_count == 1


def test_session_all_insufficient_is_insufficient() -> None:
    cases = [
        _case_result(Verdict.INSUFFICIENT, 0.0),
        _case_result(Verdict.INSUFFICIENT, 0.0),
    ]
    sv = resolve_session(cases, falsifiability_score=0.0)
    assert sv.session_verdict is Verdict.INSUFFICIENT


def test_session_empty_is_insufficient() -> None:
    sv = resolve_session([], falsifiability_score=0.0)
    assert sv.session_verdict is Verdict.INSUFFICIENT
    assert sv.case_count == 0
