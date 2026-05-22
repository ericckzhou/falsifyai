"""Tests for the Paraphrase perturbation family.

Paraphrase generates semantic-preserving rewrites via an LLM, validates each
via embedding cosine similarity, and retries on validity failure up to
``max_attempts`` per requested paraphrase. Phase B of the validation
campaign — see ``dev_notes/plans/PR-22-paraphrase-perturbation.md``.

RED phase: these tests describe the public surface before it exists.
"""

import pytest

from falsifyai.perturbation.base import PerturbationCategory
from falsifyai.spec.models import ModelConfig
from tests.fixtures.mock_adapter import MockAdapter
from tests.fixtures.mock_embedder import MockEmbedder

# Common test inputs
_ORIG = "What is the capital of France?"
_GOOD_PARAPHRASES = [
    "Which city is the capital of France?",
    "Name France's capital city.",
    "Tell me the capital of France.",
    "What city serves as France's capital?",
    "Which is the French capital?",
]


def _model_config() -> ModelConfig:
    return ModelConfig(
        provider="mock",
        model="mock-paraphraser",
        temperature=0.7,
        max_tokens=64,
    )


def _identical_embedding_map(texts: list[str]) -> dict[str, list[float]]:
    """All texts mapped to the same unit vector -> cosine similarity 1.0."""
    return {t: [1.0, 0.0, 0.0] for t in texts}


def _orthogonal_embedding_map(originals: list[str], perturbed: list[str]) -> dict[str, list[float]]:
    """Originals on x-axis, perturbed on y-axis -> cosine similarity 0.0."""
    return {**{t: [1.0, 0.0, 0.0] for t in originals},
            **{t: [0.0, 1.0, 0.0] for t in perturbed}}


# ---------------------------------------------------------------------------
# Class shape + metadata
# ---------------------------------------------------------------------------


def test_paraphrase_has_correct_classvars() -> None:
    """Static metadata matches the Perturbation Protocol."""
    from falsifyai.perturbation.paraphrase import Paraphrase

    assert Paraphrase.name == "paraphrase"
    assert Paraphrase.category is PerturbationCategory.SEMANTIC
    # LLM-driven; not deterministic in the same sense as typo_noise (whose
    # output is determined by the seed alone). For paraphrase the
    # determinism guarantee is that the materialized spec persists the
    # result, not that re-calling apply() produces the same output.
    assert Paraphrase.is_deterministic is False
    assert Paraphrase.is_local is False  # external LLM service


# ---------------------------------------------------------------------------
# apply() — happy path
# ---------------------------------------------------------------------------


def test_apply_produces_requested_count_when_all_valid() -> None:
    """When every paraphrase passes the validity gate, apply() returns `count` PerturbedInputs."""
    from falsifyai.perturbation.paraphrase import Paraphrase

    # MockAdapter returns a different valid-looking response for each call
    response_iter = iter(_GOOD_PARAPHRASES)
    adapter = MockAdapter(default_response="placeholder")
    # Override execute to return the next paraphrase in sequence
    adapter.response_map = {}  # ignore prompt-keyed lookups
    original_execute = adapter.execute
    def stateful_execute(request):
        # Inject a fresh paraphrase per call by mutating default_response
        adapter.default_response = next(response_iter, "I cannot paraphrase.")
        return original_execute(request)
    adapter.execute = stateful_execute  # type: ignore[method-assign]

    embedder = MockEmbedder(
        response_map=_identical_embedding_map([_ORIG] + _GOOD_PARAPHRASES)
    )
    p = Paraphrase(
        count=3,
        similarity_threshold=0.5,
        max_attempts=3,
        model_config=_model_config(),
        adapter=adapter,
        embedder=embedder,
    )
    result = p.apply(_ORIG, seed=42)
    assert len(result) == 3
    # Each result is a PerturbedInput from the paraphrase family
    for pi in result:
        assert pi.lineage.perturbation_type == "paraphrase"
        assert pi.lineage.category is PerturbationCategory.SEMANTIC
        assert pi.lineage.seed == 42


def test_apply_lineage_includes_sample_index_and_requested_count() -> None:
    """Lineage carries sample_index, requested_count, similarity_threshold, and model name."""
    from falsifyai.perturbation.paraphrase import Paraphrase

    response_iter = iter(_GOOD_PARAPHRASES)
    adapter = MockAdapter(default_response="placeholder")
    adapter.response_map = {}
    original_execute = adapter.execute
    def stateful_execute(request):
        adapter.default_response = next(response_iter, "Cannot.")
        return original_execute(request)
    adapter.execute = stateful_execute  # type: ignore[method-assign]

    embedder = MockEmbedder(response_map=_identical_embedding_map([_ORIG] + _GOOD_PARAPHRASES))
    p = Paraphrase(
        count=2,
        similarity_threshold=0.5,
        max_attempts=3,
        model_config=_model_config(),
        adapter=adapter,
        embedder=embedder,
    )
    result = p.apply(_ORIG, seed=42)

    assert [pi.lineage.params["sample_index"] for pi in result] == [0, 1]
    for pi in result:
        assert pi.lineage.params["requested_count"] == 2
        assert pi.lineage.params["similarity_threshold"] == 0.5
        assert pi.lineage.params["model"] == "mock-paraphraser"


def test_apply_each_paraphrase_triggers_a_distinct_llm_call() -> None:
    """The MockAdapter should record one call per accepted paraphrase."""
    from falsifyai.perturbation.paraphrase import Paraphrase

    response_iter = iter(_GOOD_PARAPHRASES)
    adapter = MockAdapter(default_response="placeholder")
    adapter.response_map = {}
    original_execute = adapter.execute
    def stateful_execute(request):
        adapter.default_response = next(response_iter, "Cannot.")
        return original_execute(request)
    adapter.execute = stateful_execute  # type: ignore[method-assign]

    embedder = MockEmbedder(response_map=_identical_embedding_map([_ORIG] + _GOOD_PARAPHRASES))
    p = Paraphrase(
        count=3,
        similarity_threshold=0.5,
        max_attempts=3,
        model_config=_model_config(),
        adapter=adapter,
        embedder=embedder,
    )
    p.apply(_ORIG, seed=42)
    # Exactly 3 LLM calls — one per accepted paraphrase
    assert adapter.call_count == 3


# ---------------------------------------------------------------------------
# apply() — validity gating + retries
# ---------------------------------------------------------------------------


def test_apply_retries_when_paraphrase_fails_validity() -> None:
    """When a paraphrase fails validity, apply() retries up to max_attempts.

    First call returns a low-similarity output (orthogonal vector); second
    call returns a good one. The first should be dropped and the second
    accepted, yielding 1 valid paraphrase total with 2 LLM calls.
    """
    from falsifyai.perturbation.paraphrase import Paraphrase

    bad = "I cannot answer that."
    good = "Tell me the capital of France."
    responses = iter([bad, good])
    adapter = MockAdapter()
    adapter.response_map = {}
    original_execute = adapter.execute
    def stateful_execute(request):
        adapter.default_response = next(responses, "Cannot.")
        return original_execute(request)
    adapter.execute = stateful_execute  # type: ignore[method-assign]

    embedder = MockEmbedder(
        response_map={
            _ORIG: [1.0, 0.0, 0.0],  # x-axis
            bad: [0.0, 1.0, 0.0],   # y-axis -> cos similarity 0 vs original
            good: [1.0, 0.0, 0.0],  # parallel -> cos similarity 1
        }
    )
    p = Paraphrase(
        count=1,
        similarity_threshold=0.5,
        max_attempts=3,
        model_config=_model_config(),
        adapter=adapter,
        embedder=embedder,
    )
    result = p.apply(_ORIG, seed=42)
    assert len(result) == 1
    assert result[0].text == good
    # 1 bad attempt + 1 good attempt = 2 calls
    assert adapter.call_count == 2


def test_apply_gives_up_after_max_attempts_and_returns_fewer_than_count() -> None:
    """If max_attempts is exhausted on a sample, drop it and move to the next.

    Per PR-22 plan decision D1 — the result list can be shorter than the
    requested count when generation can't produce valid outputs.
    """
    from falsifyai.perturbation.paraphrase import Paraphrase

    # Every response is below the validity threshold
    bad = "I cannot do that."
    adapter = MockAdapter(default_response=bad)
    embedder = MockEmbedder(
        response_map={
            _ORIG: [1.0, 0.0, 0.0],
            bad: [0.0, 1.0, 0.0],  # orthogonal -> cos similarity 0
        }
    )
    p = Paraphrase(
        count=3,
        similarity_threshold=0.5,
        max_attempts=2,
        model_config=_model_config(),
        adapter=adapter,
        embedder=embedder,
    )
    result = p.apply(_ORIG, seed=42)
    # All 3 samples failed; result is empty
    assert len(result) == 0
    # 3 samples * 2 max_attempts = 6 total calls
    assert adapter.call_count == 6


def test_apply_records_attempts_used_per_sample() -> None:
    """Lineage on each accepted paraphrase records how many attempts were used."""
    from falsifyai.perturbation.paraphrase import Paraphrase

    bad = "I cannot."
    good = "Which city is France's capital?"
    # Sample 0: good on first try (1 attempt)
    # Sample 1: bad, then good (2 attempts)
    responses = iter([good, bad, good])
    adapter = MockAdapter()
    adapter.response_map = {}
    original_execute = adapter.execute
    def stateful_execute(request):
        adapter.default_response = next(responses, "Cannot.")
        return original_execute(request)
    adapter.execute = stateful_execute  # type: ignore[method-assign]

    embedder = MockEmbedder(
        response_map={
            _ORIG: [1.0, 0.0, 0.0],
            bad: [0.0, 1.0, 0.0],
            good: [1.0, 0.0, 0.0],
        }
    )
    p = Paraphrase(
        count=2,
        similarity_threshold=0.5,
        max_attempts=3,
        model_config=_model_config(),
        adapter=adapter,
        embedder=embedder,
    )
    result = p.apply(_ORIG, seed=42)
    assert len(result) == 2
    assert result[0].lineage.params["attempts_used"] == 1
    assert result[1].lineage.params["attempts_used"] == 2


# ---------------------------------------------------------------------------
# validate()
# ---------------------------------------------------------------------------


def test_validate_accepts_high_similarity_paraphrase() -> None:
    from falsifyai.perturbation.paraphrase import Paraphrase

    embedder = MockEmbedder(
        response_map={
            _ORIG: [1.0, 0.0, 0.0],
            "Which city is the capital of France?": [1.0, 0.0, 0.0],
        }
    )
    p = Paraphrase(
        count=1,
        similarity_threshold=0.85,
        max_attempts=1,
        model_config=_model_config(),
        adapter=MockAdapter(),
        embedder=embedder,
    )
    result = p.validate(_ORIG, "Which city is the capital of France?")
    assert result.is_valid is True
    assert result.validity_score == pytest.approx(1.0)
    assert result.method == "embedding_cosine"


def test_validate_rejects_low_similarity_paraphrase() -> None:
    from falsifyai.perturbation.paraphrase import Paraphrase

    embedder = MockEmbedder(
        response_map={
            _ORIG: [1.0, 0.0, 0.0],
            "I cannot.": [0.0, 1.0, 0.0],
        }
    )
    p = Paraphrase(
        count=1,
        similarity_threshold=0.85,
        max_attempts=1,
        model_config=_model_config(),
        adapter=MockAdapter(),
        embedder=embedder,
    )
    result = p.validate(_ORIG, "I cannot.")
    assert result.is_valid is False
    assert result.validity_score == pytest.approx(0.0)


def test_validate_threshold_is_configurable() -> None:
    """A 0.7 similarity passes at threshold=0.6 but fails at threshold=0.85."""
    from falsifyai.perturbation.paraphrase import Paraphrase

    # Construct vectors with cosine similarity ~ 0.7
    import numpy as np

    v1 = np.array([1.0, 0.0, 0.0])
    v2 = np.array([0.7, 0.7141428, 0.0])  # cos angle ~ 0.7
    embedder = MockEmbedder(response_map={"A": list(v1), "B": list(v2)})

    lenient = Paraphrase(
        count=1, similarity_threshold=0.6, max_attempts=1,
        model_config=_model_config(), adapter=MockAdapter(), embedder=embedder,
    )
    assert lenient.validate("A", "B").is_valid is True

    strict = Paraphrase(
        count=1, similarity_threshold=0.85, max_attempts=1,
        model_config=_model_config(), adapter=MockAdapter(), embedder=embedder,
    )
    assert strict.validate("A", "B").is_valid is False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_paraphrase_resolved_by_build_perturbation() -> None:
    """build_perturbation(ParaphrasePerturbationSpec) returns a Paraphrase instance.

    Registry needs primary_model + adapter passed through (paraphrase needs
    LLM access). This is the architectural change in this PR — the registry
    now accepts optional kwargs that pure perturbations ignore.
    """
    from falsifyai.perturbation import build_perturbation
    from falsifyai.perturbation.paraphrase import Paraphrase
    from falsifyai.spec.models import ParaphrasePerturbationSpec

    spec = ParaphrasePerturbationSpec(type="paraphrase", count=4)
    primary = _model_config()
    adapter = MockAdapter()
    embedder = MockEmbedder()
    instance = build_perturbation(
        spec,
        primary_model=primary,
        adapter=adapter,
        embedder=embedder,
    )
    assert isinstance(instance, Paraphrase)
    assert instance.count == 4
    assert instance.model_config == primary  # used spec.model since spec.paraphrase.model is None


def test_paraphrase_spec_model_override_takes_precedence() -> None:
    """When paraphrase.model is set on the spec, it overrides primary_model."""
    from falsifyai.perturbation import build_perturbation
    from falsifyai.spec.models import ParaphrasePerturbationSpec

    override = ModelConfig(provider="groq", model="paraphraser-override", temperature=0.5, max_tokens=128)
    spec = ParaphrasePerturbationSpec(type="paraphrase", count=2, model=override)
    primary = _model_config()
    instance = build_perturbation(
        spec,
        primary_model=primary,
        adapter=MockAdapter(),
        embedder=MockEmbedder(),
    )
    assert instance.model_config == override


def test_paraphrase_requires_model_in_registry() -> None:
    """ValueError if neither paraphrase.model nor primary_model is supplied."""
    from falsifyai.perturbation import build_perturbation
    from falsifyai.spec.models import ParaphrasePerturbationSpec

    spec = ParaphrasePerturbationSpec(type="paraphrase", count=1)
    with pytest.raises(ValueError, match="paraphrase.*model"):
        build_perturbation(
            spec,
            primary_model=None,
            adapter=MockAdapter(),
            embedder=MockEmbedder(),
        )


def test_paraphrase_requires_adapter_in_registry() -> None:
    """ValueError if no adapter is supplied for paraphrase."""
    from falsifyai.perturbation import build_perturbation
    from falsifyai.spec.models import ParaphrasePerturbationSpec

    spec = ParaphrasePerturbationSpec(type="paraphrase", count=1)
    with pytest.raises(ValueError, match=r"(?i)paraphrase.*adapter"):
        build_perturbation(
            spec,
            primary_model=_model_config(),
            adapter=None,
            embedder=MockEmbedder(),
        )
