"""Tests for falsifyai.invariants.contains.ContainsInvariant."""

import pytest

from falsifyai.invariants.base import Severity
from falsifyai.invariants.contains import ContainsInvariant


def _check(
    inv: ContainsInvariant,
    perturbed: str,
    *,
    original: str = "<ignored>",
):
    return inv.check(original_output=original, perturbed_output=perturbed, context={})


def test_all_values_present_passes() -> None:
    inv = ContainsInvariant(values=["Paris"], severity=Severity.HIGH)
    result = _check(inv, "The answer is Paris, of course.")
    assert result.passed is True
    assert result.score == 1.0


def test_value_missing_fails() -> None:
    inv = ContainsInvariant(values=["Paris"], severity=Severity.HIGH)
    result = _check(inv, "I don't know.")
    assert result.passed is False
    assert result.score == 0.0


def test_partial_presence_yields_fractional_score() -> None:
    inv = ContainsInvariant(values=["Paris", "France", "capital"], severity=Severity.HIGH)
    result = _check(inv, "Paris is the capital.")  # 2 of 3 present
    assert result.passed is False  # all-or-nothing on passed
    assert result.score == pytest.approx(2 / 3)


def test_case_insensitive_by_default() -> None:
    inv = ContainsInvariant(values=["Paris"], severity=Severity.HIGH)
    result = _check(inv, "the answer is paris")  # lowercase
    assert result.passed is True


def test_case_sensitive_when_requested() -> None:
    inv = ContainsInvariant(values=["Paris"], severity=Severity.HIGH, case_sensitive=True)
    miss = _check(inv, "the answer is paris")  # wrong case
    hit = _check(inv, "the answer is Paris")
    assert miss.passed is False
    assert hit.passed is True


def test_original_output_is_ignored() -> None:
    """ContainsInvariant is a per-output assertion; the original shouldn't affect it."""
    inv = ContainsInvariant(values=["Paris"], severity=Severity.HIGH)
    a = _check(inv, "Paris", original="completely different")
    b = _check(inv, "Paris", original="Paris is the capital")
    assert a.passed is True and b.passed is True
    assert a.score == b.score


def test_protocol_attributes() -> None:
    inv = ContainsInvariant(values=["x"], severity=Severity.CRITICAL)
    assert inv.name == "contains"
    assert inv.severity is Severity.CRITICAL


def test_result_carries_invariant_name_and_severity() -> None:
    inv = ContainsInvariant(values=["Paris"], severity=Severity.CRITICAL)
    result = _check(inv, "Paris")
    assert result.invariant_name == "contains"
    assert result.severity is Severity.CRITICAL


def test_falsifiability_contribution_scales_with_value_length() -> None:
    """Per plan section 10.1: min(1.0, sum(len(v) for v in values) / 50)."""
    short = ContainsInvariant(values=["a"], severity=Severity.HIGH)
    medium = ContainsInvariant(values=["Paris"], severity=Severity.HIGH)
    long = ContainsInvariant(
        values=["x" * 30, "y" * 30], severity=Severity.HIGH
    )  # 60 chars -> capped at 1.0
    assert short.falsifiability_contribution() == 1 / 50
    assert medium.falsifiability_contribution() == 5 / 50
    assert long.falsifiability_contribution() == 1.0


def test_evidence_lists_missing_values() -> None:
    inv = ContainsInvariant(values=["Paris", "France"], severity=Severity.HIGH)
    result = _check(inv, "Paris but not the country")
    assert "missing" in result.evidence
    assert "France" in result.evidence["missing"]  # type: ignore[operator]
