"""Tests for falsifyai.verdict.consistency — lightweight CONSISTENTLY_WRONG detection.

Per [plan.md section 2.3](../../plan.md): a confidently hallucinating model
that gives the same wrong answer to every variant of a question is the most
dangerous production case. The placeholder calls this STABLE; the real
resolver must catch it.

The MVP detection is pure string-match against ground truth:
- expected.contains: model's outputs must contain the required strings;
  if every output (original + perturbed) misses them, the model is
  consistently wrong.
- expected.not_contains: every output must avoid the forbidden strings;
  if every output contains a forbidden string, the model is consistently
  wrong about NOT mentioning it.

Embedding-based reference contradiction (expected.reference) is deferred
to the full ConsistencyOracle in Phase 1.
"""

from falsifyai.spec.models import ExpectedSection
from falsifyai.verdict.consistency import is_consistently_wrong


def test_no_ground_truth_returns_false() -> None:
    """No expected.contains, no expected.not_contains -> nothing to falsify against."""
    expected = ExpectedSection()
    assert is_consistently_wrong("any output", ["any other"], expected) is False


def test_contains_all_outputs_miss_required_value() -> None:
    expected = ExpectedSection(contains=["Paris"])
    original = "London is the capital of France."
    perturbed = ["London.", "It's London.", "Definitely London."]
    assert is_consistently_wrong(original, perturbed, expected) is True


def test_contains_one_output_has_the_required_value() -> None:
    expected = ExpectedSection(contains=["Paris"])
    original = "London is the capital of France."
    perturbed = ["London.", "Paris.", "Definitely London."]  # one mentions Paris
    assert is_consistently_wrong(original, perturbed, expected) is False


def test_not_contains_every_output_has_forbidden_value() -> None:
    expected = ExpectedSection(not_contains=["London"])
    original = "London is the capital of France."
    perturbed = ["London.", "It's London."]
    assert is_consistently_wrong(original, perturbed, expected) is True


def test_not_contains_one_output_avoids_forbidden_value() -> None:
    expected = ExpectedSection(not_contains=["London"])
    original = "London is the capital of France."
    perturbed = ["London.", "Paris.", "London."]  # one avoids London
    assert is_consistently_wrong(original, perturbed, expected) is False


def test_contains_check_is_case_insensitive() -> None:
    """Match ContainsInvariant's default case_sensitive=False behavior."""
    expected = ExpectedSection(contains=["Paris"])
    original = "PARIS is the capital."  # uppercase
    perturbed = ["paris.", "Paris!"]
    assert is_consistently_wrong(original, perturbed, expected) is False


def test_contains_requires_all_values_missing_across_all_outputs() -> None:
    """expected.contains: ['Paris', 'France'] -- partial answers don't qualify."""
    expected = ExpectedSection(contains=["Paris", "France"])
    # Every output mentions France but never Paris; only Paris is missing.
    # Behavior: "missing ANY required value across ALL outputs" -> wrong.
    original = "France is a country."
    perturbed = ["France.", "Yes France.", "France indeed."]
    assert is_consistently_wrong(original, perturbed, expected) is True


def test_original_satisfies_but_perturbed_drift_is_not_consistently_wrong() -> None:
    """If only perturbed outputs drift, it's FRAGILE, not CONSISTENTLY_WRONG."""
    expected = ExpectedSection(contains=["Paris"])
    original = "Paris is the capital of France."  # correct
    perturbed = ["London.", "I don't know.", "Tokyo."]  # all wrong
    # Original is fine -> not consistently wrong (model knows the answer
    # sometimes; that's FRAGILE).
    assert is_consistently_wrong(original, perturbed, expected) is False
