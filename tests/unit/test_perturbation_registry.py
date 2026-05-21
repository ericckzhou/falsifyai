"""Tests for falsifyai.perturbation.registry.build_perturbation."""

import pytest

from falsifyai.perturbation.casing_variant import CasingVariant
from falsifyai.perturbation.registry import build_perturbation
from falsifyai.perturbation.typo_noise import TypoNoise
from falsifyai.spec.models import CasingVariantSpec, TypoNoiseSpec


def test_build_typo_noise_propagates_count_and_rate() -> None:
    spec = TypoNoiseSpec(type="typo_noise", count=7, rate=0.2)
    perturbation = build_perturbation(spec)
    assert isinstance(perturbation, TypoNoise)
    assert perturbation.count == 7
    assert perturbation.rate == 0.2


def test_build_casing_variant_propagates_variants() -> None:
    spec = CasingVariantSpec(type="casing", variants=["upper", "lower"])
    perturbation = build_perturbation(spec)
    assert isinstance(perturbation, CasingVariant)
    assert perturbation.variants == ["upper", "lower"]


def test_build_unknown_spec_raises_value_error() -> None:
    class _Fake:
        pass

    with pytest.raises(ValueError, match="Unknown perturbation spec"):
        build_perturbation(_Fake())  # type: ignore[arg-type]


def test_round_trip_default_specs_produce_usable_runtimes() -> None:
    """End-to-end: default spec models build runtimes that apply() successfully."""
    typo = build_perturbation(TypoNoiseSpec(type="typo_noise"))
    casing = build_perturbation(CasingVariantSpec(type="casing"))
    typo_out = typo.apply("test input", seed=1)
    casing_out = casing.apply("test input", seed=1)
    assert len(typo_out) == 5  # TypoNoiseSpec default count
    assert len(casing_out) == 3  # CasingVariantSpec default variants
