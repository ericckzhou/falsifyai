"""CasingVariant perturbation -- whole-text casing transformations."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, Literal

from falsifyai.perturbation.base import (
    PerturbationCategory,
    PerturbationLineage,
    PerturbedInput,
    ValidityResult,
    hash_input,
)

CasingMode = Literal["upper", "lower", "title"]

_TRANSFORMS: dict[str, Callable[[str], str]] = {
    "upper": str.upper,
    "lower": str.lower,
    "title": str.title,
}


@dataclass(frozen=True)
class CasingVariant:
    """Apply casing transformations: ``upper``, ``lower``, ``title``.

    Note: ``variants=["upper", "lower", "title"]`` applied to ``"hello"``
    yields ``["HELLO", "hello", "Hello"]`` -- the middle is identical to the
    input. This is intentional: the user asked for that variant explicitly.
    """

    variants: list[CasingMode] = field(default_factory=lambda: ["upper", "lower", "title"])

    name: ClassVar[str] = "casing"
    category: ClassVar[PerturbationCategory] = PerturbationCategory.LEXICAL
    is_deterministic: ClassVar[bool] = True
    is_local: ClassVar[bool] = True

    def apply(self, input_text: str, seed: int) -> list[PerturbedInput]:
        parent_hash = hash_input(input_text)
        results: list[PerturbedInput] = []
        for sample_index, variant in enumerate(self.variants):
            text = _TRANSFORMS[variant](input_text)
            lineage = PerturbationLineage(
                perturbation_type=self.name,
                category=self.category,
                method=variant,
                seed=seed,
                params={
                    "sample_index": sample_index,
                    "variant": variant,
                },
                parent_input_hash=parent_hash,
            )
            results.append(
                PerturbedInput(
                    text=text,
                    lineage=lineage,
                    validity_score=1.0,
                    metadata={},
                )
            )
        return results

    def validate(self, original: str, perturbed: str) -> ValidityResult:
        if original.lower() == perturbed.lower():
            return ValidityResult(
                is_valid=True,
                validity_score=1.0,
                reason="Casing transformation preserves content",
                method="lowercase_equality",
            )
        return ValidityResult(
            is_valid=False,
            validity_score=0.0,
            reason="Perturbed differs from original ignoring case",
            method="lowercase_equality",
        )
