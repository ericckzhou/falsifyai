"""Perturbation layer -- runtime impls + registry."""

from falsifyai.perturbation.base import (
    Perturbation,
    PerturbationCategory,
    PerturbationLineage,
    PerturbedInput,
    ValidityResult,
    hash_input,
)
from falsifyai.perturbation.casing_variant import CasingVariant
from falsifyai.perturbation.registry import build_perturbation
from falsifyai.perturbation.typo_noise import TypoNoise

__all__ = [
    "CasingVariant",
    "Perturbation",
    "PerturbationCategory",
    "PerturbationLineage",
    "PerturbedInput",
    "TypoNoise",
    "ValidityResult",
    "build_perturbation",
    "hash_input",
]
