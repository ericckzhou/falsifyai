"""Tests for falsifyai.perturbation.typo_noise."""

from falsifyai.perturbation.base import PerturbationCategory, hash_input
from falsifyai.perturbation.typo_noise import TypoNoise


def test_apply_produces_count_samples() -> None:
    perturbation = TypoNoise(count=5, rate=0.1)
    out = perturbation.apply("What is the capital of France?", seed=42)
    assert len(out) == 5


def test_apply_is_deterministic_for_same_seed() -> None:
    perturbation = TypoNoise(count=3, rate=0.1)
    a = perturbation.apply("Hello, world.", seed=42)
    b = perturbation.apply("Hello, world.", seed=42)
    assert [pi.text for pi in a] == [pi.text for pi in b]


def test_apply_differs_for_different_seeds() -> None:
    perturbation = TypoNoise(count=5, rate=0.2)
    a = perturbation.apply("Hello, world. This is a longer test string.", seed=42)
    b = perturbation.apply("Hello, world. This is a longer test string.", seed=99)
    # At least one sample must differ between seeds
    assert any(x.text != y.text for x, y in zip(a, b, strict=True))


def test_lineage_records_provenance() -> None:
    perturbation = TypoNoise(count=2, rate=0.1)
    out = perturbation.apply("Hello.", seed=7)
    for pi in out:
        assert pi.lineage.perturbation_type == "typo_noise"
        assert pi.lineage.category == PerturbationCategory.LEXICAL
        assert pi.lineage.seed == 7
        assert pi.lineage.method == "character_mutations"
        assert pi.lineage.parent_input_hash == hash_input("Hello.")


def test_lineage_includes_sample_index_for_replay_determinism() -> None:
    """params['sample_index'] is required per the reproducibility convention."""
    perturbation = TypoNoise(count=4, rate=0.1)
    out = perturbation.apply("Hello, world.", seed=42)
    indices = [pi.lineage.params["sample_index"] for pi in out]
    assert indices == [0, 1, 2, 3]


def test_lineage_params_include_rate_and_count() -> None:
    perturbation = TypoNoise(count=3, rate=0.25)
    out = perturbation.apply("Hello.", seed=1)
    for pi in out:
        assert pi.lineage.params["rate"] == 0.25
        assert pi.lineage.params["count"] == 3


def test_protocol_attributes() -> None:
    p = TypoNoise()
    assert p.name == "typo_noise"
    assert p.category == PerturbationCategory.LEXICAL
    assert p.is_deterministic is True
    assert p.is_local is True


def test_apply_handles_empty_input() -> None:
    perturbation = TypoNoise(count=3, rate=0.1)
    out = perturbation.apply("", seed=1)
    assert len(out) == 3
    for pi in out:
        assert pi.text == ""


def test_apply_handles_single_character_input() -> None:
    perturbation = TypoNoise(count=2, rate=0.5)
    out = perturbation.apply("X", seed=1)
    assert len(out) == 2


def test_validate_identical_strings_passes() -> None:
    result = TypoNoise(count=1, rate=0.1).validate("Hello", "Hello")
    assert result.is_valid is True
    assert result.validity_score == 1.0


def test_validate_within_budget_passes() -> None:
    # 1 char different out of 5 = 20% normalized; budget = 2 * 0.2 = 40%
    result = TypoNoise(count=1, rate=0.2).validate("Hello", "Hallo")
    assert result.is_valid is True


def test_validate_exceeds_budget_fails() -> None:
    # Totally different short string, tight rate
    result = TypoNoise(count=1, rate=0.05).validate("Hello", "XYZ")
    assert result.is_valid is False


def test_validate_handles_empty_original() -> None:
    """Empty original must not divide by zero."""
    result = TypoNoise(count=1, rate=0.1).validate("", "")
    assert result.is_valid is True


def test_validate_method_field() -> None:
    result = TypoNoise(count=1, rate=0.1).validate("Hello", "Hello")
    assert result.method == "edit_distance"


def test_per_sample_validity_in_metadata() -> None:
    perturbation = TypoNoise(count=3, rate=0.1)
    out = perturbation.apply("This is a longer string for testing.", seed=42)
    for pi in out:
        assert "validity" in pi.metadata
        assert 0.0 <= pi.validity_score <= 1.0


def test_mutation_count_recorded_in_lineage() -> None:
    """Per-sample mutation count is recorded so callers can audit."""
    perturbation = TypoNoise(count=3, rate=0.5)
    out = perturbation.apply("Hello, world. This is a longer string.", seed=42)
    for pi in out:
        assert "mutation_count" in pi.lineage.params
        assert isinstance(pi.lineage.params["mutation_count"], int)
