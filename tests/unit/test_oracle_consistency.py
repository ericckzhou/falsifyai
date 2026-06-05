"""Tests for falsifyai.oracles.consistency.ConsistencyOracle."""

import numpy as np

from falsifyai.oracles.base import OracleContext, OracleVerdict
from falsifyai.oracles.consistency import ConsistencyOracle, _mean_pairwise_cosine
from falsifyai.spec.models import ExpectedSection
from falsifyai.verdict.models import Verdict


class _MockEmbedder:
    """Deterministic embedder: maps known strings to fixed vectors."""

    def __init__(self, mapping: dict[str, list[float]], default: list[float] | None = None) -> None:
        self.mapping = mapping
        self.default = default or [1.0, 0.0, 0.0]

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.array([self.mapping.get(t, self.default) for t in texts], dtype=np.float64)


def _ctx(original, perturbed, expected, embedder=None):
    return OracleContext(
        original_output=original,
        perturbed_outputs=perturbed,
        expected=expected,
        embedder=embedder,
    )


# --- ground-truth path -------------------------------------------------------


def test_contains_violated_everywhere_triggers() -> None:
    expected = ExpectedSection(contains=["Paris"])
    ctx = _ctx("London", ["London.", "Still London"], expected)
    v = ConsistencyOracle().evaluate(ctx)
    assert v.triggered is True
    assert v.verdict_contribution is Verdict.CONSISTENTLY_WRONG
    assert v.confidence == 1.0
    assert v.oracle_name == "consistency"


def test_not_contains_present_everywhere_triggers() -> None:
    expected = ExpectedSection(not_contains=["sorry"])
    ctx = _ctx("I'm sorry", ["sorry again", "so sorry"], expected)
    v = ConsistencyOracle().evaluate(ctx)
    assert v.triggered is True
    assert v.verdict_contribution is Verdict.CONSISTENTLY_WRONG


def test_one_correct_output_does_not_trigger() -> None:
    """If even one output is right, it's not *consistently* wrong."""
    expected = ExpectedSection(contains=["Paris"])
    ctx = _ctx("London", ["Paris is correct", "London"], expected)
    v = ConsistencyOracle().evaluate(ctx)
    assert v.triggered is False
    assert v.verdict_contribution is None


# --- reference-agreement (embedding) path ------------------------------------


def test_embedding_agreement_contradicting_reference_triggers() -> None:
    expected = ExpectedSection(reference="The capital is Paris")
    embedder = _MockEmbedder(
        {
            "London": [1.0, 0.0, 0.0],
            "London.": [1.0, 0.0, 0.0],
            "The capital is Paris": [0.0, 1.0, 0.0],  # orthogonal -> contradicts
        }
    )
    ctx = _ctx("London", ["London."], expected, embedder=embedder)
    v = ConsistencyOracle().evaluate(ctx)
    assert v.triggered is True
    assert v.verdict_contribution is Verdict.CONSISTENTLY_WRONG
    assert v.confidence >= 0.9


def test_embedding_agreement_with_reference_does_not_trigger() -> None:
    """High agreement that *matches* the reference is correct, not wrong."""
    expected = ExpectedSection(reference="Paris")
    embedder = _MockEmbedder(
        {
            "Paris": [1.0, 0.0, 0.0],
            "Paris.": [1.0, 0.0, 0.0],
        }
    )
    ctx = _ctx("Paris", ["Paris."], expected, embedder=embedder)
    v = ConsistencyOracle().evaluate(ctx)
    assert v.triggered is False
    assert v.verdict_contribution is None


def test_embedding_disagreement_does_not_trigger() -> None:
    expected = ExpectedSection(reference="Paris")
    embedder = _MockEmbedder(
        {
            "a": [1.0, 0.0, 0.0],
            "b": [0.0, 1.0, 0.0],  # orthogonal to 'a' -> low agreement
            "Paris": [0.0, 0.0, 1.0],
        }
    )
    ctx = _ctx("a", ["b"], expected, embedder=embedder)
    v = ConsistencyOracle().evaluate(ctx)
    assert v.triggered is False


# --- null path ---------------------------------------------------------------


def test_no_violation_no_embedder_does_not_trigger() -> None:
    expected = ExpectedSection(contains=["Paris"])
    ctx = _ctx("Paris", ["Paris indeed"], expected)  # all correct
    v = ConsistencyOracle().evaluate(ctx)
    assert v.triggered is False
    assert v.confidence == 0.0
    assert isinstance(v, OracleVerdict)


# --- helper ------------------------------------------------------------------


def test_mean_pairwise_cosine_single_vector_is_one() -> None:
    assert _mean_pairwise_cosine(np.array([[1.0, 2.0, 3.0]])) == 1.0


def test_mean_pairwise_cosine_orthogonal_is_zero() -> None:
    vecs = np.array([[1.0, 0.0], [0.0, 1.0]])
    assert _mean_pairwise_cosine(vecs) == 0.0


def test_oracle_context_all_outputs() -> None:
    ctx = _ctx("orig", ["a", "b"], ExpectedSection())
    assert ctx.all_outputs == ["orig", "a", "b"]
