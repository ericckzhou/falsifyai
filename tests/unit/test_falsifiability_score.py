"""Tests for falsifyai.falsifiability.score.

Per plan.md section 15: every invariant exposes a falsifiability_contribution
in [0, 1]. Case score = mean across invariants. Suite score = mean across
cases. A low suite score is the framework's defense against passing CI with
toothless assertions like contains: ["a"].
"""

import pytest

from falsifyai.falsifiability.score import (
    LOW_FALSIFIABILITY_THRESHOLD,
    case_falsifiability,
    suite_falsifiability,
)
from falsifyai.invariants.base import Severity
from falsifyai.invariants.contains import ContainsInvariant
from falsifyai.invariants.semantic import SemanticEquivalenceInvariant


def test_empty_invariants_yields_zero() -> None:
    assert case_falsifiability([]) == 0.0


def test_single_invariant_returns_its_contribution() -> None:
    inv = ContainsInvariant(values=["Paris"], severity=Severity.HIGH)
    expected = inv.falsifiability_contribution()
    assert case_falsifiability([inv]) == pytest.approx(expected)


def test_mean_across_multiple_invariants() -> None:
    contains = ContainsInvariant(values=["Paris"], severity=Severity.HIGH)
    semantic = SemanticEquivalenceInvariant(threshold=0.85, severity=Severity.HIGH)
    expected = (contains.falsifiability_contribution() + semantic.falsifiability_contribution()) / 2
    assert case_falsifiability([contains, semantic]) == pytest.approx(expected)


def test_suite_falsifiability_is_mean_of_case_scores() -> None:
    assert suite_falsifiability([0.4, 0.6, 0.8]) == pytest.approx(0.6)


def test_suite_falsifiability_empty_yields_zero() -> None:
    assert suite_falsifiability([]) == 0.0


def test_threshold_constant_matches_plan_default() -> None:
    """Plan section 15 default threshold for warnings."""
    assert LOW_FALSIFIABILITY_THRESHOLD == 0.5
