"""TypoNoise perturbation -- character-level mutations.

Each character position is mutated independently with probability ``rate``,
using one of: drop, insert, substitute, transpose. Resulting edit distance
is bounded around ``len(input) * rate``.
"""

import string
from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from falsifyai.perturbation.base import (
    PerturbationCategory,
    PerturbationLineage,
    PerturbedInput,
    ValidityResult,
    hash_input,
)

_INSERT_VOCAB = string.ascii_lowercase + " "


@dataclass(frozen=True)
class TypoNoise:
    """Character-level mutations: drop, insert, substitute, transpose."""

    count: int = 5
    rate: float = 0.05

    name: ClassVar[str] = "typo_noise"
    category: ClassVar[PerturbationCategory] = PerturbationCategory.LEXICAL
    is_deterministic: ClassVar[bool] = True
    is_local: ClassVar[bool] = True

    def apply(self, input_text: str, seed: int) -> list[PerturbedInput]:
        rng = np.random.default_rng(seed)
        parent_hash = hash_input(input_text)
        results: list[PerturbedInput] = []
        for sample_index in range(self.count):
            text, mutation_count = self._mutate_once(input_text, rng)
            validity = self._validity_from_count(input_text, mutation_count)
            lineage = PerturbationLineage(
                perturbation_type=self.name,
                category=self.category,
                method="character_mutations",
                seed=seed,
                params={
                    "sample_index": sample_index,
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
        return results

    def validate(self, original: str, perturbed: str) -> ValidityResult:
        distance = _levenshtein(original, perturbed)
        denom = max(len(original), 1)
        normalized = distance / denom
        is_valid = normalized <= 2.0 * self.rate
        score = max(0.0, 1.0 - normalized)
        return ValidityResult(
            is_valid=is_valid,
            validity_score=score,
            reason=(
                f"edit_distance={distance}, normalized={normalized:.3f}, "
                f"budget={2.0 * self.rate:.3f}"
            ),
            method="edit_distance",
        )

    def _mutate_once(self, text: str, rng: np.random.Generator) -> tuple[str, int]:
        """Apply per-character mutations probabilistically.

        Returns (mutated_text, count_of_mutations_applied).
        """
        if not text:
            return "", 0
        chars: list[str] = []
        mutation_count = 0
        i = 0
        n = len(text)
        while i < n:
            if rng.random() < self.rate:
                op = int(rng.integers(0, 4))
                if op == 0:
                    # drop current
                    mutation_count += 1
                    i += 1
                    continue
                if op == 1:
                    # insert random char before current
                    chars.append(_INSERT_VOCAB[int(rng.integers(0, len(_INSERT_VOCAB)))])
                    chars.append(text[i])
                    mutation_count += 1
                    i += 1
                    continue
                if op == 2:
                    # substitute current with random char
                    chars.append(_INSERT_VOCAB[int(rng.integers(0, len(_INSERT_VOCAB)))])
                    mutation_count += 1
                    i += 1
                    continue
                if op == 3 and i + 1 < n:
                    # transpose current with next
                    chars.append(text[i + 1])
                    chars.append(text[i])
                    mutation_count += 1
                    i += 2
                    continue
            chars.append(text[i])
            i += 1
        return "".join(chars), mutation_count

    def _validity_from_count(self, original: str, mutation_count: int) -> ValidityResult:
        """Cheap per-sample validity using the known mutation count."""
        denom = max(len(original), 1)
        normalized = mutation_count / denom
        is_valid = normalized <= 2.0 * self.rate
        score = max(0.0, 1.0 - normalized)
        return ValidityResult(
            is_valid=is_valid,
            validity_score=score,
            reason=(
                f"mutation_count={mutation_count}, normalized={normalized:.3f}, "
                f"budget={2.0 * self.rate:.3f}"
            ),
            method="mutation_count",
        )


def _levenshtein(a: str, b: str) -> int:
    """Levenshtein distance via DP with O(min(len(a), len(b))) memory."""
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            insertions = previous[j] + 1
            deletions = current[j - 1] + 1
            substitutions = previous[j - 1] + (0 if ca == cb else 1)
            current.append(min(insertions, deletions, substitutions))
        previous = current
    return previous[-1]
