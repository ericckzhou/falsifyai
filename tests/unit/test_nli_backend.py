"""Unit tests for the NLI backend primitive (PR-I).

The real ``TransformersNLIBackend`` is never asked to ``classify()`` here -- that
would download ~500MB of deberta weights. We test:

- ``MockNLIBackend`` determinism + its documented substring/rules contract,
- Protocol conformance for both backends,
- that constructing the real backend does NOT load the model (laziness),
- that reaching the real backend without ``transformers`` raises a friendly error.
"""

import sys

import pytest

from falsifyai.oracles.nli import (
    MockNLIBackend,
    NLIBackend,
    NLILabel,
    NLIResult,
    TransformersNLIBackend,
)


class TestNLIResult:
    def test_label_and_scores_and_version_round_trip(self) -> None:
        result = NLIResult(
            label=NLILabel.ENTAILMENT,
            scores={
                NLILabel.ENTAILMENT: 0.9,
                NLILabel.NEUTRAL: 0.07,
                NLILabel.CONTRADICTION: 0.03,
            },
            model_version="mock-nli-v1",
        )
        assert result.label is NLILabel.ENTAILMENT
        assert result.scores[NLILabel.ENTAILMENT] == 0.9
        assert result.model_version == "mock-nli-v1"

    def test_three_labels_exist(self) -> None:
        assert {m.value for m in NLILabel} == {"entailment", "neutral", "contradiction"}


class TestMockDeterminism:
    def test_same_input_same_output(self) -> None:
        mock = MockNLIBackend()
        a = mock.classify("Paris is the capital of France.", "Paris is the capital.")
        b = mock.classify("Paris is the capital of France.", "Paris is the capital.")
        assert a == b

    def test_non_substring_hypothesis_is_neutral(self) -> None:
        mock = MockNLIBackend()
        result = mock.classify("The capital of France is Paris.", "Berlin is in Germany")
        # hypothesis is not a literal substring -> neutral by default heuristic
        assert result.label is NLILabel.NEUTRAL

    def test_literal_substring_is_entailment(self) -> None:
        mock = MockNLIBackend()
        result = mock.classify("The capital of France is Paris.", "capital of France")
        assert result.label is NLILabel.ENTAILMENT

    def test_chosen_label_has_highest_score(self) -> None:
        mock = MockNLIBackend()
        result = mock.classify("anything", "unrelated hypothesis")
        assert max(result.scores, key=result.scores.get) is result.label

    def test_scores_sum_to_one(self) -> None:
        mock = MockNLIBackend()
        result = mock.classify("anything", "unrelated")
        assert result.scores[NLILabel.ENTAILMENT] + result.scores[NLILabel.NEUTRAL] + result.scores[
            NLILabel.CONTRADICTION
        ] == pytest.approx(1.0)


class TestMockControls:
    def test_default_label_forces_all_pairs(self) -> None:
        mock = MockNLIBackend(default_label=NLILabel.CONTRADICTION)
        assert mock.classify("a", "b").label is NLILabel.CONTRADICTION
        assert mock.classify("x is true", "x is true").label is NLILabel.CONTRADICTION

    def test_rules_override_per_pair(self) -> None:
        mock = MockNLIBackend(
            rules={("ref", "out1"): NLILabel.ENTAILMENT, ("ref", "out2"): NLILabel.CONTRADICTION}
        )
        assert mock.classify("ref", "out1").label is NLILabel.ENTAILMENT
        assert mock.classify("ref", "out2").label is NLILabel.CONTRADICTION

    def test_rules_take_precedence_over_default_label(self) -> None:
        mock = MockNLIBackend(
            default_label=NLILabel.NEUTRAL,
            rules={("p", "h"): NLILabel.ENTAILMENT},
        )
        assert mock.classify("p", "h").label is NLILabel.ENTAILMENT
        assert mock.classify("p", "other").label is NLILabel.NEUTRAL

    def test_mock_has_model_version(self) -> None:
        assert MockNLIBackend().model_version == "mock-nli-v1"


class TestProtocolConformance:
    def test_mock_is_nli_backend(self) -> None:
        assert isinstance(MockNLIBackend(), NLIBackend)

    def test_transformers_backend_is_nli_backend(self) -> None:
        assert isinstance(TransformersNLIBackend(), NLIBackend)


class TestLazyLoad:
    def test_construction_does_not_load_model(self) -> None:
        backend = TransformersNLIBackend()
        # Cheap construction: no model object materialized yet.
        assert backend._model is None

    def test_model_version_known_before_load(self) -> None:
        backend = TransformersNLIBackend(model_name="cross-encoder/nli-deberta-v3-small")
        assert backend.model_version == "cross-encoder/nli-deberta-v3-small"
        assert backend._model is None


class TestFriendlyError:
    def test_missing_transformers_raises_helpful_importerror(self, monkeypatch) -> None:
        # Simulate transformers not being installed: importing it raises ImportError.
        monkeypatch.setitem(sys.modules, "transformers", None)
        backend = TransformersNLIBackend()
        with pytest.raises(ImportError, match=r"falsifyai\[nli\]"):
            backend.classify("a premise", "a hypothesis")
