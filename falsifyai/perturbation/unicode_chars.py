"""UnicodePerturbation -- visually-identical, byte-different inputs.

This family exposes a failure mode no other perturbation can: input that a
human reads as *identical* to the original but that is a different byte string.
It is the generation-side complement to case study 01 (a U+202F narrow
no-break space silently swapped for an ASCII space), which FalsifyAI could
previously *detect* but not *generate*.

Three orthogonal mechanisms, all producing the same failure mode:

- ``invisible_space``: substitute an ASCII space (U+0020) with a Unicode space
  variant (NBSP, narrow/thin/figure space). Renders identically; different byte.
  This is the exact CS-01 mechanism (U+202F).
- ``zero_width``: insert a zero-width character (ZWSP, ZWNJ, ZWNBSP/BOM) between
  characters. Invisible; changes length and bytes.
- ``homoglyph``: substitute a Latin letter with a Cyrillic/Greek confusable
  (e.g. ``a`` -> U+0430 CYRILLIC SMALL LETTER A). Visually identical glyph.

Category is ADVERSARIAL, not LEXICAL: unlike ``typo_noise`` (which produces
*visible* corruption), these inputs are indistinguishable to a human reader.
That is precisely what makes a model's sensitivity to them a reliability defect
rather than an expected response to a malformed prompt.

Validity is high by construction. Each mechanism only swaps a character for a
visual/semantic equivalent, so the perturbed text preserves the original's
intent. :meth:`UnicodePerturbation.validate` confirms this independently by
reversing the substitution and comparing to the original.

Reproducibility: ``apply`` emits ``len(methods) * count`` samples and stamps a
unique ``params["sample_index"]`` on every one, per the convention in
``perturbation/base.py``.
"""

from dataclasses import dataclass, field
from typing import ClassVar, Literal

import numpy as np

from falsifyai.perturbation.base import (
    PerturbationCategory,
    PerturbationLineage,
    PerturbedInput,
    ValidityResult,
    hash_input,
)

UnicodeMethod = Literal["invisible_space", "zero_width", "homoglyph"]

# Unicode space characters that render like an ASCII space but carry a
# different code point. U+202F (narrow no-break space) is the CS-01 culprit.
_SPACE_VARIANTS: tuple[str, ...] = (
    " ",  # NO-BREAK SPACE
    " ",  # FIGURE SPACE
    " ",  # THIN SPACE
    " ",  # NARROW NO-BREAK SPACE  (case study 01)
)

# Zero-width characters: invisible, no advance width.
_ZERO_WIDTH: tuple[str, ...] = (
    "​",  # ZERO WIDTH SPACE
    "‌",  # ZERO WIDTH NON-JOINER
    "﻿",  # ZERO WIDTH NO-BREAK SPACE (BOM)
)

# Latin -> visually-confusable Cyrillic/Greek code points.
_HOMOGLYPHS: dict[str, str] = {
    "a": "а",  # CYRILLIC SMALL LETTER A
    "c": "с",  # CYRILLIC SMALL LETTER ES
    "e": "е",  # CYRILLIC SMALL LETTER IE
    "i": "і",  # CYRILLIC SMALL LETTER BYELORUSSIAN-UKRAINIAN I
    "o": "о",  # CYRILLIC SMALL LETTER O
    "p": "р",  # CYRILLIC SMALL LETTER ER
    "x": "х",  # CYRILLIC SMALL LETTER HA
    "y": "у",  # CYRILLIC SMALL LETTER U
}

# Inverse map for the validity check: every character this perturbation can
# introduce maps back to its ASCII source (zero-width chars map to "").
_REVERSE: dict[str, str] = {
    **{variant: " " for variant in _SPACE_VARIANTS},
    **{zw: "" for zw in _ZERO_WIDTH},
    **{glyph: latin for latin, glyph in _HOMOGLYPHS.items()},
}

_DEFAULT_METHODS: tuple[UnicodeMethod, ...] = ("invisible_space", "zero_width", "homoglyph")


@dataclass(frozen=True)
class UnicodePerturbation:
    """Substitute characters with visually-identical Unicode equivalents.

    Each method in ``methods`` produces ``count`` samples; ``rate`` controls
    the fraction of eligible positions mutated per sample.
    """

    methods: list[UnicodeMethod] = field(default_factory=lambda: list(_DEFAULT_METHODS))
    count: int = 3
    rate: float = 0.5

    name: ClassVar[str] = "unicode"
    category: ClassVar[PerturbationCategory] = PerturbationCategory.ADVERSARIAL
    is_deterministic: ClassVar[bool] = True
    is_local: ClassVar[bool] = True

    def apply(self, input_text: str, seed: int) -> list[PerturbedInput]:
        rng = np.random.default_rng(seed)
        parent_hash = hash_input(input_text)
        results: list[PerturbedInput] = []
        sample_index = 0
        for method in self.methods:
            for _ in range(self.count):
                text, mutation_count = self._apply_method(method, input_text, rng)
                validity = self._validity(input_text, text)
                lineage = PerturbationLineage(
                    perturbation_type=self.name,
                    category=self.category,
                    method=method,
                    seed=seed,
                    params={
                        "sample_index": sample_index,
                        "method": method,
                        "rate": self.rate,
                        "count": self.count,
                        "mutation_count": mutation_count,
                    },
                    parent_input_hash=parent_hash,
                )
                results.append(
                    PerturbedInput(
                        text=text,
                        lineage=lineage,
                        validity_score=validity.validity_score,
                        metadata={"validity": validity},
                    )
                )
                sample_index += 1
        return results

    def validate(self, original: str, perturbed: str) -> ValidityResult:
        """Reverse the substitution; a valid perturbation recovers the original.

        Because every introduced character has a known ASCII source, undoing
        the mapping must reproduce ``original`` exactly. Anything else means a
        character was changed that this perturbation does not own.
        """
        recovered = _deperturb(perturbed)
        if recovered == original:
            return ValidityResult(
                is_valid=True,
                validity_score=1.0,
                reason="Substitution reverses cleanly to the original",
                method="reverse_substitution",
            )
        return ValidityResult(
            is_valid=False,
            validity_score=0.0,
            reason="Perturbed text does not reverse to the original",
            method="reverse_substitution",
        )

    def _apply_method(
        self, method: UnicodeMethod, text: str, rng: np.random.Generator
    ) -> tuple[str, int]:
        if method == "invisible_space":
            return self._substitute_spaces(text, rng)
        if method == "zero_width":
            return self._insert_zero_width(text, rng)
        if method == "homoglyph":
            return self._substitute_homoglyphs(text, rng)
        raise ValueError(f"Unknown unicode method: {method!r}")

    def _substitute_spaces(self, text: str, rng: np.random.Generator) -> tuple[str, int]:
        chars: list[str] = []
        count = 0
        for ch in text:
            if ch == " " and rng.random() < self.rate:
                chars.append(_SPACE_VARIANTS[int(rng.integers(0, len(_SPACE_VARIANTS)))])
                count += 1
            else:
                chars.append(ch)
        return "".join(chars), count

    def _insert_zero_width(self, text: str, rng: np.random.Generator) -> tuple[str, int]:
        if not text:
            return "", 0
        chars: list[str] = []
        count = 0
        # Insert *between* characters only, so the result still reverses cleanly
        # and we never lead/trail with an invisible char.
        for i, ch in enumerate(text):
            chars.append(ch)
            if i < len(text) - 1 and rng.random() < self.rate:
                chars.append(_ZERO_WIDTH[int(rng.integers(0, len(_ZERO_WIDTH)))])
                count += 1
        return "".join(chars), count

    def _substitute_homoglyphs(self, text: str, rng: np.random.Generator) -> tuple[str, int]:
        chars: list[str] = []
        count = 0
        for ch in text:
            glyph = _HOMOGLYPHS.get(ch)
            if glyph is not None and rng.random() < self.rate:
                chars.append(glyph)
                count += 1
            else:
                chars.append(ch)
        return "".join(chars), count

    def _validity(self, original: str, perturbed: str) -> ValidityResult:
        return self.validate(original, perturbed)


def _deperturb(text: str) -> str:
    """Map every introduced Unicode character back to its ASCII source."""
    return "".join(_REVERSE.get(ch, ch) for ch in text)
