"""Tests for falsifyai.perturbation.casing_variant."""

from falsifyai.perturbation.base import PerturbationCategory, hash_input
from falsifyai.perturbation.casing_variant import CasingVariant


def test_apply_produces_one_per_variant() -> None:
    perturbation = CasingVariant(variants=["upper", "lower", "title"])
    out = perturbation.apply("Hello, World.", seed=0)
    assert len(out) == 3


def test_apply_upper_uppercases() -> None:
    out = CasingVariant(variants=["upper"]).apply("Hello, World.", seed=0)
    assert out[0].text == "HELLO, WORLD."


def test_apply_lower_lowercases() -> None:
    out = CasingVariant(variants=["lower"]).apply("Hello, World.", seed=0)
    assert out[0].text == "hello, world."


def test_apply_title_title_cases() -> None:
    out = CasingVariant(variants=["title"]).apply("hello, world.", seed=0)
    assert out[0].text == "Hello, World."


def test_apply_is_independent_of_seed() -> None:
    """Casing is deterministic regardless of seed."""
    perturbation = CasingVariant(variants=["upper", "lower"])
    a = perturbation.apply("Hello", seed=42)
    b = perturbation.apply("Hello", seed=999)
    assert [pi.text for pi in a] == [pi.text for pi in b]


def test_lineage_records_provenance() -> None:
    perturbation = CasingVariant(variants=["upper", "lower"])
    out = perturbation.apply("Hello", seed=7)
    for pi in out:
        assert pi.lineage.perturbation_type == "casing"
        assert pi.lineage.category == PerturbationCategory.LEXICAL
        assert pi.lineage.seed == 7
        assert pi.lineage.parent_input_hash == hash_input("Hello")


def test_lineage_method_matches_variant() -> None:
    out = CasingVariant(variants=["upper", "lower", "title"]).apply("Hi", seed=0)
    methods = [pi.lineage.method for pi in out]
    assert methods == ["upper", "lower", "title"]


def test_lineage_includes_sample_index_for_replay_determinism() -> None:
    """params['sample_index'] is required per the reproducibility convention."""
    out = CasingVariant(variants=["upper", "lower", "title"]).apply("Hi", seed=0)
    indices = [pi.lineage.params["sample_index"] for pi in out]
    assert indices == [0, 1, 2]


def test_validity_score_is_one() -> None:
    out = CasingVariant(variants=["upper", "lower", "title"]).apply("Hello", seed=0)
    for pi in out:
        assert pi.validity_score == 1.0


def test_protocol_attributes() -> None:
    p = CasingVariant()
    assert p.name == "casing"
    assert p.category == PerturbationCategory.LEXICAL
    assert p.is_deterministic is True
    assert p.is_local is True


def test_validate_casing_only_change_passes() -> None:
    result = CasingVariant(variants=["upper"]).validate("Hello", "HELLO")
    assert result.is_valid is True
    assert result.validity_score == 1.0


def test_validate_content_change_fails() -> None:
    result = CasingVariant(variants=["upper"]).validate("Hello", "Goodbye")
    assert result.is_valid is False
    assert result.validity_score == 0.0


def test_validate_method_field() -> None:
    result = CasingVariant(variants=["upper"]).validate("Hello", "HELLO")
    assert result.method == "lowercase_equality"


def test_idempotent_variant_still_emitted() -> None:
    """variants=['lower'] on already-lowercase produces an identical sample (intentional)."""
    out = CasingVariant(variants=["lower"]).apply("hello", seed=0)
    assert len(out) == 1
    assert out[0].text == "hello"


def test_default_variants() -> None:
    p = CasingVariant()
    assert p.variants == ["upper", "lower", "title"]
