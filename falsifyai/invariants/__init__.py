"""Invariant layer -- runtime impls + registry.

Public surface for callers:

    from falsifyai.invariants import (
        Invariant, InvariantResult, Severity,
        ContainsInvariant, SemanticEquivalenceInvariant,
        EmbeddingBackend, SentenceTransformerBackend,
        build_invariant,
    )
"""

from falsifyai.invariants.base import (
    EmbeddingBackend,
    Invariant,
    InvariantResult,
    Severity,
)
from falsifyai.invariants.contains import ContainsInvariant
from falsifyai.invariants.registry import build_invariant
from falsifyai.invariants.semantic import (
    SemanticEquivalenceInvariant,
    SentenceTransformerBackend,
)

__all__ = [
    "ContainsInvariant",
    "EmbeddingBackend",
    "Invariant",
    "InvariantResult",
    "SemanticEquivalenceInvariant",
    "SentenceTransformerBackend",
    "Severity",
    "build_invariant",
]
