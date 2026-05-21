"""Tests for falsifyai.invariants.base -- Protocol, dataclass, enum, embedding-backend Protocol."""

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from falsifyai.invariants.base import (
    EmbeddingBackend,
    InvariantResult,
    Severity,
)


def test_severity_has_four_members() -> None:
    assert {s.value for s in Severity} == {"critical", "high", "medium", "low"}


def test_invariant_result_is_frozen() -> None:
    result = InvariantResult(
        invariant_name="x",
        passed=True,
        score=1.0,
        details="ok",
        severity=Severity.HIGH,
    )
    with pytest.raises(FrozenInstanceError):
        result.passed = False  # type: ignore[misc]


def test_invariant_result_default_evidence_is_empty() -> None:
    result = InvariantResult(
        invariant_name="x",
        passed=True,
        score=1.0,
        details="ok",
        severity=Severity.HIGH,
    )
    assert result.evidence == {}


def test_invariant_result_score_can_be_none() -> None:
    """Some invariants (e.g. boolean checks) may not have a meaningful numeric score."""
    result = InvariantResult(
        invariant_name="x",
        passed=True,
        score=None,
        details="ok",
        severity=Severity.LOW,
    )
    assert result.score is None


def test_class_with_embed_method_satisfies_embedding_backend_protocol() -> None:
    """runtime_checkable Protocol -- isinstance() works on any class with the right attrs."""

    class FakeBackend:
        def embed(self, texts: list[str]) -> np.ndarray:
            return np.zeros((len(texts), 4))

    assert isinstance(FakeBackend(), EmbeddingBackend)


def test_class_without_embed_does_not_satisfy_embedding_backend() -> None:
    class NotAnEmbedder:
        def something_else(self) -> None: ...

    assert not isinstance(NotAnEmbedder(), EmbeddingBackend)
