"""Bidirectional-NLI perturbation validity gate — case study 06 regression.

Cosine similarity cannot catch a paraphrase that *omits* the original's
load-bearing content while keeping its vocabulary: the two texts still embed
close together. ``BidirectionalNLIValidator`` adds the entailment check that
does — a valid rewrite must entail the original AND be entailed by it, and an
omission breaks the reverse direction.

These tests pin the validator in isolation, its integration into the
``Paraphrase`` gate (cosine passes, NLI rejects), the byte-identical
cosine-only fallback when no NLI backend is present, and the ``build_perturbation``
wiring that turns an injected NLI backend into a validator.
"""

import pytest

from falsifyai.oracles.nli import MockNLIBackend, NLILabel
from falsifyai.perturbation.paraphrase import Paraphrase
from falsifyai.perturbation.validity import BidirectionalNLIValidator
from falsifyai.spec.models import ModelConfig
from tests.fixtures.mock_adapter import MockAdapter
from tests.fixtures.mock_embedder import MockEmbedder

# The case-study substrate, compressed. A faithful paraphrase preserves meaning
# both directions; an omission paraphrase drops the delete/export clauses, so
# the original entails it but it does NOT entail the original.
_ORIG = "All users may read. Only administrators may delete. No user may export."
_FAITHFUL = "Reading is open to all; deletion is admin-only; nobody may export."
_OMISSION = "For a standard user the allowed action is read."


def _model_config() -> ModelConfig:
    return ModelConfig(provider="mock", model="mock-paraphraser", temperature=0.0, max_tokens=64)


# --- BidirectionalNLIValidator in isolation --------------------------------


def test_validator_accepts_bidirectional_entailment() -> None:
    nli = MockNLIBackend(
        rules={
            (_ORIG, _FAITHFUL): NLILabel.ENTAILMENT,
            (_FAITHFUL, _ORIG): NLILabel.ENTAILMENT,
        }
    )
    result = BidirectionalNLIValidator(nli).validate(_ORIG, _FAITHFUL)
    assert result.is_valid is True
    assert result.method == "nli_bidirectional"
    assert result.validity_score == pytest.approx(0.9)


def test_validator_rejects_omission_one_directional_entailment() -> None:
    """Original entails the shorter perturbed, but perturbed does NOT entail the
    original (it dropped the delete/export clauses) → reject."""
    nli = MockNLIBackend(
        rules={
            (_ORIG, _OMISSION): NLILabel.ENTAILMENT,
            (_OMISSION, _ORIG): NLILabel.NEUTRAL,
        }
    )
    result = BidirectionalNLIValidator(nli).validate(_ORIG, _OMISSION)
    assert result.is_valid is False
    assert result.validity_score < 0.7  # weakest direction governs the score


# --- Paraphrase gate: cosine passes, NLI rejects ---------------------------


def test_paraphrase_gate_nli_overrides_high_cosine_omission() -> None:
    """The case-study failure: an omission paraphrase passes cosine (topically
    near-identical, similarity 1.0) but is rejected once NLI is wired in."""
    embedder = MockEmbedder(response_map={_ORIG: [1.0, 0.0, 0.0], _OMISSION: [1.0, 0.0, 0.0]})
    nli = MockNLIBackend(
        rules={(_ORIG, _OMISSION): NLILabel.ENTAILMENT, (_OMISSION, _ORIG): NLILabel.NEUTRAL}
    )
    p = Paraphrase(
        count=1,
        similarity_threshold=0.85,
        max_attempts=1,
        model_config=_model_config(),
        adapter=MockAdapter(),
        embedder=embedder,
        nli_validator=BidirectionalNLIValidator(nli),
    )
    result = p.validate(_ORIG, _OMISSION)
    assert result.is_valid is False  # cosine=1.0 alone would have passed
    assert result.method == "embedding_cosine+nli_bidirectional"


def test_paraphrase_gate_without_nli_is_cosine_only_unchanged() -> None:
    """No NLI validator → behavior byte-identical to the cosine-only gate."""
    embedder = MockEmbedder(response_map={_ORIG: [1.0, 0.0, 0.0], _OMISSION: [1.0, 0.0, 0.0]})
    p = Paraphrase(
        count=1,
        similarity_threshold=0.85,
        max_attempts=1,
        model_config=_model_config(),
        adapter=MockAdapter(),
        embedder=embedder,
    )
    result = p.validate(_ORIG, _OMISSION)
    assert result.is_valid is True
    assert result.method == "embedding_cosine"


# --- build_perturbation wiring ---------------------------------------------


def test_build_perturbation_wires_nli_validator_when_backend_present() -> None:
    from falsifyai.perturbation import build_perturbation
    from falsifyai.spec.models import ParaphrasePerturbationSpec

    spec = ParaphrasePerturbationSpec(type="paraphrase", count=1)
    instance = build_perturbation(
        spec,
        primary_model=_model_config(),
        adapter=MockAdapter(),
        embedder=MockEmbedder(),
        nli_backend=MockNLIBackend(default_label=NLILabel.ENTAILMENT),
    )
    assert isinstance(instance, Paraphrase)
    assert isinstance(instance.nli_validator, BidirectionalNLIValidator)


def test_build_perturbation_no_nli_validator_without_backend() -> None:
    from falsifyai.perturbation import build_perturbation
    from falsifyai.spec.models import ParaphrasePerturbationSpec

    spec = ParaphrasePerturbationSpec(type="paraphrase", count=1)
    instance = build_perturbation(
        spec,
        primary_model=_model_config(),
        adapter=MockAdapter(),
        embedder=MockEmbedder(),
    )
    assert isinstance(instance, Paraphrase)
    assert instance.nli_validator is None
