"""Perturbation Protocol + supporting dataclasses + category enum.

See plan.md sections 5.1 and 9 for the full design.

Reproducibility convention
--------------------------
Every perturbation that emits more than one output from a single call to
:meth:`Perturbation.apply` MUST stamp ``params["sample_index"]: int`` on each
:class:`PerturbationLineage` it produces. Combined with ``lineage.seed`` this
gives a unique, replay-stable identity to every sample. Phase 0 honors this
even when sample_index is degenerate (e.g., ``CasingVariant`` where the
variant name already disambiguates) so the convention is uniform across all
perturbation types.
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class PerturbationCategory(Enum):
    LEXICAL = "lexical"
    SYNTACTIC = "syntactic"
    SEMANTIC = "semantic"
    CONTEXTUAL = "contextual"
    ADVERSARIAL = "adversarial"


@dataclass(frozen=True)
class PerturbationLineage:
    """Provenance for one perturbed input.

    ``params`` must include ``"sample_index"`` (int) when the parent
    perturbation emits multiple outputs from a single ``apply()`` call.
    See the module docstring's reproducibility convention.
    """

    perturbation_type: str
    category: PerturbationCategory
    method: str
    seed: int
    params: dict[str, object]
    parent_input_hash: str


@dataclass(frozen=True)
class ValidityResult:
    """Whether (and how strongly) a perturbed text preserves the original's intent."""

    is_valid: bool
    validity_score: float
    reason: str
    method: str


@dataclass(frozen=True)
class PerturbedInput:
    """One candidate perturbed input + its provenance + validity score."""

    text: str
    lineage: PerturbationLineage
    validity_score: float
    metadata: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class Perturbation(Protocol):
    """Runtime interface for a perturbation strategy."""

    name: str
    category: PerturbationCategory
    is_deterministic: bool
    is_local: bool

    def apply(self, input_text: str, seed: int) -> list[PerturbedInput]:
        """Apply the perturbation, returning all candidate variants.

        Implementations that emit multiple outputs MUST include
        ``"sample_index"`` in each lineage's ``params``.
        """
        ...

    def validate(self, original: str, perturbed: str) -> ValidityResult:
        """Decide whether ``perturbed`` preserves the intent of ``original``."""
        ...


def hash_input(text: str) -> str:
    """sha256 of the input text; populates ``PerturbationLineage.parent_input_hash``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
