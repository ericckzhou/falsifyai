"""Tests for falsifyai.perturbation.unicode_chars."""

from falsifyai.perturbation.base import PerturbationCategory, hash_input
from falsifyai.perturbation.unicode_chars import (
    _SPACE_VARIANTS,
    _ZERO_WIDTH,
    UnicodePerturbation,
    _deperturb,
)

_SENTENCE = "What is the capital of France?"


def test_protocol_attributes() -> None:
    p = UnicodePerturbation()
    assert p.name == "unicode"
    assert p.category == PerturbationCategory.ADVERSARIAL
    assert p.is_deterministic is True
    assert p.is_local is True


def test_default_methods() -> None:
    assert UnicodePerturbation().methods == ["invisible_space", "zero_width", "homoglyph"]


def test_apply_emits_count_per_method() -> None:
    p = UnicodePerturbation(methods=["invisible_space", "homoglyph"], count=4)
    out = p.apply(_SENTENCE, seed=0)
    assert len(out) == 2 * 4


def test_sample_index_is_unique_and_contiguous() -> None:
    """params['sample_index'] must be globally unique across all emitted samples."""
    p = UnicodePerturbation(methods=["invisible_space", "zero_width", "homoglyph"], count=3)
    out = p.apply(_SENTENCE, seed=7)
    indices = [pi.lineage.params["sample_index"] for pi in out]
    assert indices == list(range(len(out)))


def test_determinism_same_seed_same_outputs() -> None:
    p = UnicodePerturbation(count=3)
    a = p.apply(_SENTENCE, seed=42)
    b = p.apply(_SENTENCE, seed=42)
    assert [pi.text for pi in a] == [pi.text for pi in b]


def test_lineage_records_provenance() -> None:
    p = UnicodePerturbation(methods=["invisible_space"], count=2)
    out = p.apply(_SENTENCE, seed=5)
    for pi in out:
        assert pi.lineage.perturbation_type == "unicode"
        assert pi.lineage.category == PerturbationCategory.ADVERSARIAL
        assert pi.lineage.seed == 5
        assert pi.lineage.parent_input_hash == hash_input(_SENTENCE)
        assert pi.lineage.method == "invisible_space"
        assert "mutation_count" in pi.lineage.params


def test_invisible_space_swaps_spaces_but_reverses_to_original() -> None:
    """The CS-01 mechanism: spaces become Unicode variants; text differs by bytes only."""
    p = UnicodePerturbation(methods=["invisible_space"], count=1, rate=1.0)
    out = p.apply(_SENTENCE, seed=3)
    text = out[0].text
    assert text != _SENTENCE  # byte-different
    assert any(variant in text for variant in _SPACE_VARIANTS)  # contains a Unicode space
    assert " " not in text  # all ASCII spaces were replaced (rate=1.0)
    assert _deperturb(text) == _SENTENCE  # renders/means identically


def test_invisible_space_can_reproduce_narrow_no_break_space() -> None:
    """U+202F (the CS-01 culprit) is reachable from the invisible_space method."""
    p = UnicodePerturbation(methods=["invisible_space"], count=20, rate=1.0)
    out = p.apply(_SENTENCE, seed=1)
    assert any(" " in pi.text for pi in out)


def test_zero_width_inserts_invisible_chars() -> None:
    p = UnicodePerturbation(methods=["zero_width"], count=1, rate=1.0)
    out = p.apply("abc", seed=1)
    text = out[0].text
    assert len(text) > len("abc")
    assert any(zw in text for zw in _ZERO_WIDTH)
    assert _deperturb(text) == "abc"


def test_homoglyph_substitutes_confusables() -> None:
    p = UnicodePerturbation(methods=["homoglyph"], count=1, rate=1.0)
    out = p.apply("paris", seed=2)
    text = out[0].text
    assert text != "paris"
    # Cyrillic homoglyphs are not in the ASCII range.
    assert any(ord(ch) > 127 for ch in text)
    assert _deperturb(text) == "paris"


def test_validity_high_by_construction() -> None:
    p = UnicodePerturbation(count=2)
    out = p.apply(_SENTENCE, seed=9)
    for pi in out:
        assert pi.validity_score == 1.0


def test_validate_clean_reversal_passes() -> None:
    p = UnicodePerturbation()
    # Construct a known-valid perturbed string from the maps so the test source
    # carries no embedded invisible literals: a Unicode space + a zero-width
    # char inserted into "the city".
    valid = "the" + _SPACE_VARIANTS[3] + "ci" + _ZERO_WIDTH[0] + "ty"
    result = p.validate("the city", valid)
    assert result.is_valid is True
    assert result.validity_score == 1.0
    assert result.method == "reverse_substitution"


def test_validate_content_change_fails() -> None:
    p = UnicodePerturbation()
    result = p.validate("Paris", "London")
    assert result.is_valid is False
    assert result.validity_score == 0.0


def test_no_eligible_positions_yields_identity() -> None:
    """A sentence with no spaces and no eligible letters reverses to itself."""
    p = UnicodePerturbation(methods=["invisible_space"], count=1, rate=1.0)
    out = p.apply("1234567", seed=0)
    assert out[0].text == "1234567"
    assert out[0].lineage.params["mutation_count"] == 0
