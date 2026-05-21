"""Tests for falsifyai.verdict.stratify.

Bootstrap CI computation + stratification by perturbation family + worst-
case selection across strata. The honest-confidence machinery that
replaces the placeholder's "passes / total" fraction.
"""

import pytest

from falsifyai.execution.models import Execution, ModelRequest
from falsifyai.invariants.base import InvariantResult, Severity
from falsifyai.perturbation.base import (
    PerturbationCategory,
    PerturbationLineage,
    PerturbedInput,
)
from falsifyai.replay.models import PerturbedRun
from falsifyai.verdict.stratify import (
    bootstrap_stability,
    stratify_by_family,
    worst_case_stratified,
)


def _execution() -> Execution:
    req = ModelRequest(
        provider="mock",
        model="mock-model",
        prompt="p",
        temperature=0.0,
        max_tokens=128,
        seed=42,
        timeout_seconds=30,
    )
    return Execution(
        request=req,
        output_text="out",
        latency_ms=1.0,
        prompt_tokens=1,
        completion_tokens=1,
        cached=False,
        seed_provided=True,
    )


def _perturbed_run(family: str, passed: bool) -> PerturbedRun:
    return PerturbedRun(
        perturbed_input=PerturbedInput(
            text="x",
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
        execution=_execution(),
        invariant_results=[
            InvariantResult(
                invariant_name="contains",
                passed=passed,
                score=1.0 if passed else 0.0,
                details="",
                severity=Severity.HIGH,
                evidence={},
            )
        ],
    )


# ---------------------------------------------------------------------------
# bootstrap_stability
# ---------------------------------------------------------------------------


def test_bootstrap_deterministic_given_seed() -> None:
    a = bootstrap_stability([True, False, True, True], seed=42)
    b = bootstrap_stability([True, False, True, True], seed=42)
    assert a == b


def test_bootstrap_all_pass_yields_perfect_estimate() -> None:
    point, lo, hi = bootstrap_stability([True, True, True, True], seed=1)
    assert point == pytest.approx(1.0)
    assert lo == pytest.approx(1.0)
    assert hi == pytest.approx(1.0)


def test_bootstrap_all_fail_yields_zero_estimate() -> None:
    point, lo, hi = bootstrap_stability([False, False, False, False], seed=1)
    assert point == pytest.approx(0.0)
    assert lo == pytest.approx(0.0)
    assert hi == pytest.approx(0.0)


def test_bootstrap_mixed_falls_within_unit_interval() -> None:
    """5 of 8 pass -> point estimate near 0.625; CI must envelope it."""
    point, lo, hi = bootstrap_stability([True, True, True, True, True, False, False, False], seed=7)
    assert 0.0 <= lo <= point <= hi <= 1.0
    assert point == pytest.approx(0.625, abs=0.001)


def test_bootstrap_empty_list_returns_zero_zero_zero() -> None:
    point, lo, hi = bootstrap_stability([], seed=1)
    assert (point, lo, hi) == (0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# stratify_by_family
# ---------------------------------------------------------------------------


def test_stratify_groups_pass_fail_by_perturbation_type() -> None:
    runs = [
        _perturbed_run("typo_noise", True),
        _perturbed_run("typo_noise", True),
        _perturbed_run("casing_variant", False),
    ]
    strata = stratify_by_family(runs)
    assert strata == {
        "typo_noise": [True, True],
        "casing_variant": [False],
    }


def test_stratify_empty_returns_empty_dict() -> None:
    assert stratify_by_family([]) == {}


def test_stratify_run_passes_iff_all_invariants_pass() -> None:
    """A perturbed run with mixed invariant results counts as a single fail."""
    req = ModelRequest(
        provider="mock",
        model="mock-model",
        prompt="p",
        temperature=0.0,
        max_tokens=128,
        seed=42,
        timeout_seconds=30,
    )
    exec_ = Execution(
        request=req,
        output_text="out",
        latency_ms=1.0,
        prompt_tokens=1,
        completion_tokens=1,
        cached=False,
        seed_provided=True,
    )
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
        execution=exec_,
        invariant_results=[
            InvariantResult("contains", True, 1.0, "", Severity.HIGH, {}),
            InvariantResult("semantic_equivalence", False, 0.2, "", Severity.HIGH, {}),
        ],
    )
    strata = stratify_by_family([run])
    assert strata == {"typo_noise": [False]}  # one invariant failed -> run failed


# ---------------------------------------------------------------------------
# worst_case_stratified
# ---------------------------------------------------------------------------


def test_worst_case_returns_family_with_lowest_ci_low() -> None:
    per_family = {
        "typo_noise": (0.9, 0.85, 0.95),
        "casing_variant": (0.4, 0.2, 0.6),
    }
    worst, point, lo, hi = worst_case_stratified(per_family)
    assert worst == "casing_variant"
    assert (point, lo, hi) == (0.4, 0.2, 0.6)


def test_worst_case_single_family() -> None:
    per_family = {"typo_noise": (0.9, 0.85, 0.95)}
    worst, point, lo, hi = worst_case_stratified(per_family)
    assert worst == "typo_noise"
    assert (point, lo, hi) == (0.9, 0.85, 0.95)


def test_worst_case_empty_returns_none_and_zeros() -> None:
    worst, point, lo, hi = worst_case_stratified({})
    assert worst is None
    assert (point, lo, hi) == (0.0, 0.0, 0.0)
