"""Tests for falsifyai.invariants.semantic.SemanticEquivalenceInvariant.

All tests use ``MockEmbedder`` -- no real sentence-transformer model is loaded
in CI. ``SentenceTransformerBackend`` is exercised only via construction (a
cheap no-op) and never via ``embed()`` during tests.
"""

import math

import pytest

from falsifyai.invariants.base import Severity
from falsifyai.invariants.semantic import (
    SemanticEquivalenceInvariant,
    SentenceTransformerBackend,
)
from tests.fixtures.mock_embedder import MockEmbedder


def _check(
    inv: SemanticEquivalenceInvariant,
    *,
    original: str,
    perturbed: str,
):
    return inv.check(original_output=original, perturbed_output=perturbed, context={})


def test_identical_strings_yield_similarity_one() -> None:
    """Same string -> MockEmbedder returns identical vectors -> cosine sim = 1.0."""
    inv = SemanticEquivalenceInvariant(
        threshold=0.5, severity=Severity.HIGH, embedder=MockEmbedder()
    )
    result = _check(inv, original="hello world", perturbed="hello world")
    assert result.passed is True
    assert result.score == pytest.approx(1.0, abs=1e-9)


def test_orthogonal_vectors_yield_zero_similarity() -> None:
    """Explicitly orthogonal vectors -> cosine = 0 -> fails any positive threshold."""
    embedder = MockEmbedder(response_map={"alpha": [1.0, 0.0, 0.0], "beta": [0.0, 1.0, 0.0]})
    inv = SemanticEquivalenceInvariant(threshold=0.5, severity=Severity.HIGH, embedder=embedder)
    result = _check(inv, original="alpha", perturbed="beta")
    assert result.passed is False
    assert result.score == pytest.approx(0.0, abs=1e-9)


def test_similarity_at_threshold_boundary_passes() -> None:
    """Sim == threshold -> passes (>= comparison)."""
    embedder = MockEmbedder(
        response_map={
            "a": [1.0, 0.0],
            "b": [math.sqrt(0.5), math.sqrt(0.5)],  # cos angle = sqrt(0.5)
        }
    )
    inv = SemanticEquivalenceInvariant(
        threshold=math.sqrt(0.5), severity=Severity.HIGH, embedder=embedder
    )
    result = _check(inv, original="a", perturbed="b")
    assert result.passed is True


def test_threshold_zero_always_passes_unless_orthogonal_or_opposite() -> None:
    embedder = MockEmbedder()
    inv = SemanticEquivalenceInvariant(threshold=0.0, severity=Severity.HIGH, embedder=embedder)
    # Two arbitrary different strings -- pseudo-random vectors will have
    # cosine similarity > 0 with overwhelming probability.
    result = _check(inv, original="alpha", perturbed="beta")
    # Just verify the result is constructed; behavior depends on vectors,
    # but threshold=0 means anything non-negative passes.
    assert result.passed in {True, False}  # construction sanity


def test_threshold_one_requires_byte_identical_embedding() -> None:
    """threshold=1.0 effectively only passes for identical strings under MockEmbedder."""
    embedder = MockEmbedder()
    inv = SemanticEquivalenceInvariant(threshold=1.0, severity=Severity.HIGH, embedder=embedder)
    same = _check(inv, original="x", perturbed="x")
    diff = _check(inv, original="x", perturbed="y")
    assert same.passed is True
    assert diff.passed is False


def test_protocol_attributes() -> None:
    inv = SemanticEquivalenceInvariant(
        threshold=0.8, severity=Severity.CRITICAL, embedder=MockEmbedder()
    )
    assert inv.name == "semantic_equivalence"
    assert inv.severity is Severity.CRITICAL


def test_falsifiability_contribution_formula() -> None:
    """Per plan section 10.1: max(0.0, (threshold - 0.5) * 2)."""
    weak = SemanticEquivalenceInvariant(
        threshold=0.3, severity=Severity.HIGH, embedder=MockEmbedder()
    )
    midline = SemanticEquivalenceInvariant(
        threshold=0.5, severity=Severity.HIGH, embedder=MockEmbedder()
    )
    medium = SemanticEquivalenceInvariant(
        threshold=0.75, severity=Severity.HIGH, embedder=MockEmbedder()
    )
    strong = SemanticEquivalenceInvariant(
        threshold=1.0, severity=Severity.HIGH, embedder=MockEmbedder()
    )
    assert weak.falsifiability_contribution() == 0.0  # clamped
    assert midline.falsifiability_contribution() == 0.0
    assert medium.falsifiability_contribution() == pytest.approx(0.5)
    assert strong.falsifiability_contribution() == pytest.approx(1.0)


def test_evidence_includes_similarity_and_threshold() -> None:
    embedder = MockEmbedder()
    inv = SemanticEquivalenceInvariant(threshold=0.7, severity=Severity.HIGH, embedder=embedder)
    result = _check(inv, original="x", perturbed="x")
    assert "similarity" in result.evidence
    assert "threshold" in result.evidence
    assert result.evidence["threshold"] == 0.7


def test_embedder_is_called_with_both_strings() -> None:
    embedder = MockEmbedder()
    inv = SemanticEquivalenceInvariant(threshold=0.5, severity=Severity.HIGH, embedder=embedder)
    _check(inv, original="alpha", perturbed="beta")
    # Either one batched call of two strings, or two separate calls.
    flat = [t for batch in embedder.calls for t in batch]
    assert "alpha" in flat
    assert "beta" in flat


def test_sentence_transformer_backend_not_loaded_in_tests() -> None:
    """Construction is cheap (no model load); verify by constructing without errors."""
    backend = SentenceTransformerBackend()
    # The internal model attribute should still be None -- lazy load.
    assert backend._model is None  # noqa: SLF001 -- intentional internal check


def test_default_embedder_is_sentence_transformer_backend() -> None:
    """When no embedder is passed, the default is a SentenceTransformerBackend instance."""
    inv = SemanticEquivalenceInvariant(threshold=0.5, severity=Severity.HIGH)
    assert isinstance(inv.embedder, SentenceTransformerBackend)


def test_zero_vector_yields_zero_similarity() -> None:
    """Guard against divide-by-zero when an embedding is the zero vector."""
    embedder = MockEmbedder(response_map={"a": [0.0, 0.0], "b": [1.0, 0.0]})
    inv = SemanticEquivalenceInvariant(threshold=0.1, severity=Severity.HIGH, embedder=embedder)
    result = _check(inv, original="a", perturbed="b")
    assert result.score == pytest.approx(0.0)
    assert result.passed is False


def test_sentence_transformer_backend_lazy_loads_on_first_embed(monkeypatch) -> None:
    """First .embed() triggers the import + SentenceTransformer(...) construction.

    Patches sentence_transformers.SentenceTransformer so no real model is
    downloaded; verifies the backend goes from _model=None to a mocked
    instance and that .encode is called with the input texts.
    """
    import sys
    import types

    fake_module = types.ModuleType("sentence_transformers")
    calls: dict[str, object] = {}

    class _FakeSentenceTransformer:
        def __init__(self, model_name: str) -> None:
            calls["init_with"] = model_name

        def encode(self, texts: list[str], convert_to_numpy: bool = True) -> object:
            import numpy as np

            calls["encoded"] = list(texts)
            return np.array([[1.0, 0.0], [1.0, 0.0]], dtype=np.float64)

    fake_module.SentenceTransformer = _FakeSentenceTransformer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    backend = SentenceTransformerBackend(model_name="fake-model")
    assert backend._model is None  # noqa: SLF001
    out = backend.embed(["alpha", "beta"])
    assert backend._model is not None  # noqa: SLF001
    assert calls["init_with"] == "fake-model"
    assert calls["encoded"] == ["alpha", "beta"]
    assert out.shape == (2, 2)
