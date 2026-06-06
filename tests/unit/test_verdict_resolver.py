"""Tests for falsifyai.verdict.resolver.

Rewrites the PR #8 placeholder tests against the real (PR #11) resolver
that does stratified bootstrap CI, lightweight CONSISTENTLY_WRONG, and
worst-case stratum surfacing.

Case-level verdict priority (worst/most-certain first):
INSUFFICIENT -> INVALID_EVAL -> CONSISTENTLY_WRONG -> [instability band:
ADVERSARIALLY_VULNERABLE | FRAGILE | AMBIGUOUS] -> [stable band:
INFORMATION_NULL | INFORMATION_PRESENT | STABLE]. The 4-verdict chain named
above is the PR #11 origin; the 0.6.x resolver emits the full 9-class taxonomy.
"""

import pytest

from falsifyai.execution.models import Execution, ModelRequest
from falsifyai.invariants.base import InvariantResult, Severity
from falsifyai.invariants.contains import ContainsInvariant
from falsifyai.oracles.nli import MockNLIBackend, NLILabel
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


def test_one_family_collapses_is_adversarially_vulnerable() -> None:
    """typo_noise all pass; casing_variant all fail -> *targeted* attack shape.

    One family holds while another reliably breaks the model: that is a known
    attack vector, ADVERSARIALLY_VULNERABLE, not the diffuse instability of
    FRAGILE. (Before the 8-verdict resolver this case resolved FRAGILE.)
    """
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
    assert result.verdict is Verdict.ADVERSARIALLY_VULNERABLE
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


def test_session_adversarially_vulnerable_beats_fragile() -> None:
    cases = [
        _case_result(Verdict.FRAGILE, 0.4),
        _case_result(Verdict.ADVERSARIALLY_VULNERABLE, 0.3),
    ]
    sv = resolve_session(cases, falsifiability_score=0.7)
    assert sv.session_verdict is Verdict.ADVERSARIALLY_VULNERABLE


def test_session_ambiguous_beats_information_null() -> None:
    cases = [_case_result(Verdict.INFORMATION_NULL, 0.9), _case_result(Verdict.AMBIGUOUS, 0.5)]
    sv = resolve_session(cases, falsifiability_score=0.7)
    assert sv.session_verdict is Verdict.AMBIGUOUS


def test_session_all_information_present_is_information_present() -> None:
    cases = [_case_result(Verdict.INFORMATION_PRESENT, 0.99) for _ in range(2)]
    sv = resolve_session(cases, falsifiability_score=0.9)
    assert sv.session_verdict is Verdict.INFORMATION_PRESENT


def test_session_mixed_present_and_stable_is_stable() -> None:
    cases = [_case_result(Verdict.INFORMATION_PRESENT, 0.99), _case_result(Verdict.STABLE, 0.96)]
    sv = resolve_session(cases, falsifiability_score=0.9)
    assert sv.session_verdict is Verdict.STABLE


# ---------------------------------------------------------------------------
# resolve_case -- the four new verdicts (PR-K)
# ---------------------------------------------------------------------------


def test_wide_ci_single_family_is_ambiguous() -> None:
    """One family, half pass: low floor but high ceiling -> can't discriminate."""
    perturbed = [
        _perturbed_run("typo_noise", "p1", "Paris.", True),
        _perturbed_run("typo_noise", "p2", "London.", False),
    ]
    result = resolve_case(
        case_id="c",
        original_input="...",
        original_execution=_exec("...", "Paris."),
        perturbed_runs=perturbed,
        expected=ExpectedSection(contains=["Paris"]),
        invariants=[ContainsInvariant(values=["Paris"], severity=Severity.HIGH)],
        stable_threshold=0.95,
        fragile_threshold=0.5,
        case_seed=CASE_SEED,
    )
    assert result.verdict is Verdict.AMBIGUOUS
    assert result.stability_ci_low < 0.95
    assert result.stability_ci_high >= 0.5


def test_stable_refusals_are_information_null() -> None:
    """Stable structure but empty content (refusals) -> INFORMATION_NULL, not STABLE."""
    refusal = "I cannot help with that."
    perturbed = [
        _perturbed_run("typo_noise", "p1", refusal, True),
        _perturbed_run("typo_noise", "p2", refusal, True),
        _perturbed_run("casing_variant", "p3", refusal, True),
    ]
    result = resolve_case(
        case_id="c",
        original_input="...",
        original_execution=_exec("...", refusal),
        perturbed_runs=perturbed,
        # No ground-truth contains (so consistency stays quiet); invariant checks a
        # token present in the refusal so every run passes -> stable region.
        expected=ExpectedSection(),
        invariants=[ContainsInvariant(values=["cannot"], severity=Severity.HIGH)],
        stable_threshold=0.95,
        case_seed=CASE_SEED,
    )
    assert result.verdict is Verdict.INFORMATION_NULL


def test_stable_and_grounded_is_information_present() -> None:
    """Stable AND the grounding oracle confirms entailment -> INFORMATION_PRESENT."""
    answer = "Paris is the capital of France."
    perturbed = [
        _perturbed_run("typo_noise", "p1", answer, True),
        _perturbed_run("typo_noise", "p2", answer, True),
        _perturbed_run("casing_variant", "p3", answer, True),
    ]
    result = resolve_case(
        case_id="c",
        original_input="...",
        original_execution=_exec("...", answer),
        perturbed_runs=perturbed,
        expected=ExpectedSection(contains=["Paris"], reference="The capital of France is Paris."),
        invariants=[ContainsInvariant(values=["Paris"], severity=Severity.HIGH)],
        stable_threshold=0.95,
        case_seed=CASE_SEED,
        nli=MockNLIBackend(default_label=NLILabel.ENTAILMENT),
    )
    assert result.verdict is Verdict.INFORMATION_PRESENT


def test_stable_without_grounding_is_plain_stable() -> None:
    """Stable but no NLI backend -> grounding can't confirm -> plain STABLE."""
    answer = "Paris."
    perturbed = [
        _perturbed_run("typo_noise", "p1", answer, True),
        _perturbed_run("casing_variant", "p2", answer, True),
    ]
    result = resolve_case(
        case_id="c",
        original_input="...",
        original_execution=_exec("...", answer),
        perturbed_runs=perturbed,
        expected=ExpectedSection(contains=["Paris"]),
        invariants=[ContainsInvariant(values=["Paris"], severity=Severity.HIGH)],
        stable_threshold=0.95,
        case_seed=CASE_SEED,
    )
    assert result.verdict is Verdict.STABLE
