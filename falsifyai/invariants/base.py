"""Invariant Protocol + supporting dataclasses + enums.

See plan.md sections 5.2 and 10 for the full design.

An ``Invariant`` is the rule that decides whether a perturbed output is still
"the same answer" as the original. Implementations like ``ContainsInvariant``
and ``SemanticEquivalenceInvariant`` ship in this module.

Embedding-using invariants (currently ``SemanticEquivalenceInvariant``) depend
on an ``EmbeddingBackend`` Protocol so tests can inject a deterministic mock
without downloading a real sentence-transformer model.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

import numpy as np


class Severity(Enum):
    """How loud a failure of this invariant should be.

    Per plan.md section 5.2:
    - CRITICAL: any failure -> case verdict is FRAGILE immediately
    - HIGH:     weighted heavily into the stability score
    - MEDIUM:   normal contribution
    - LOW:      logged but does not affect verdict
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class InvariantResult:
    """The verdict from one invariant check on one (original, perturbed) pair.

    ``score`` is optional -- boolean invariants may not have a meaningful
    numeric measure. ``evidence`` holds free-form per-invariant data (e.g.
    which values were missing for a contains-check, the cosine similarity
    for semantic equivalence).
    """

    invariant_name: str
    passed: bool
    score: float | None
    details: str
    severity: Severity
    evidence: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class Invariant(Protocol):
    """Runtime interface for an invariant strategy."""

    name: str
    severity: Severity

    def check(
        self,
        original_output: str,
        perturbed_output: str,
        context: dict[str, object],
    ) -> InvariantResult:
        """Judge whether ``perturbed_output`` still satisfies the invariant.

        Some invariants compare original vs perturbed (e.g. semantic
        equivalence); others assert per-output properties (e.g. contains
        certain strings) and ignore ``original_output``. The ``context``
        parameter is kept for forward-compat with Phase 1 oracles that need
        out-of-band info like ``expected.reference``; current invariants
        accept and ignore it.
        """
        ...

    def falsifiability_contribution(self) -> float:
        """How restrictive this invariant is, on a 0-1 scale.

        Feeds the suite-level falsifiability score downstream. Higher = more
        restrictive = harder for a model to pass trivially.
        """
        ...


@runtime_checkable
class EmbeddingBackend(Protocol):
    """Embeds strings into fixed-dimension float vectors.

    Used by ``SemanticEquivalenceInvariant`` to compute cosine similarity.
    The default impl wraps sentence-transformers; tests use a deterministic
    mock so CI never downloads a real model.
    """

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an array of shape (len(texts), embedding_dim)."""
        ...
