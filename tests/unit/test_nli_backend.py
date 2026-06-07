"""Unit tests for the NLI backend primitive (PR-I).

The real ``TransformersNLIBackend`` is never run against downloaded weights here
-- that would pull ~500MB of deberta. Its ``classify()`` wiring is exercised with
a fake ``torch`` + ``transformers`` injected into ``sys.modules`` instead. We test:

- ``MockNLIBackend`` determinism + its documented substring/rules contract,
- Protocol conformance for both backends,
- that constructing the real backend does NOT load the model (laziness),
- that reaching the real backend without ``transformers`` raises a friendly error,
- that the lazy-load success path loads once and reduces logits to the arg-max
  label (via injected fakes, no network/weights).
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


def _inject_fake_backends(monkeypatch, logits_row: list[float]) -> None:
    """Put a fake ``torch`` + ``transformers`` in ``sys.modules`` so the real
    backend's lazy load + ``classify`` run without any download.

    The fake model ignores tokenizer ``inputs`` and always returns ``logits_row``
    over the deberta label order (entailment, neutral, contradiction); the fake
    ``torch.softmax`` does a real softmax so score semantics match production.
    """
    import math
    import types

    class _NoGrad:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _softmax(row, dim=-1):
        top = max(row)
        exps = [math.exp(v - top) for v in row]
        total = sum(exps)
        return types.SimpleNamespace(tolist=lambda: [e / total for e in exps])

    fake_torch = types.ModuleType("torch")
    fake_torch.no_grad = lambda: _NoGrad()
    fake_torch.softmax = _softmax

    class _Logits:
        def __getitem__(self, _idx):
            return logits_row

    class _Output:
        logits = _Logits()

    class _Model:
        config = types.SimpleNamespace(id2label={0: "entailment", 1: "neutral", 2: "contradiction"})

        def __call__(self, **_inputs):
            return _Output()

    class _Tokenizer:
        def __call__(self, *_args, **_kwargs):
            return {}

    fake_tf = types.ModuleType("transformers")
    fake_tf.AutoTokenizer = types.SimpleNamespace(from_pretrained=lambda _name: _Tokenizer())
    fake_tf.AutoModelForSequenceClassification = types.SimpleNamespace(
        from_pretrained=lambda _name: _Model()
    )

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_tf)


class TestInjectedInferencePath:
    """Exercise the real backend's ``_load`` success + ``classify`` reduction with
    injected fakes -- covers the wiring that would otherwise need 500MB of weights."""

    def test_classify_reduces_logits_to_argmax_label(self, monkeypatch) -> None:
        _inject_fake_backends(monkeypatch, [5.0, 1.0, 0.0])  # entailment dominates
        backend = TransformersNLIBackend()
        result = backend.classify("a premise", "a hypothesis")
        assert result.label is NLILabel.ENTAILMENT
        assert result.scores[NLILabel.ENTAILMENT] == pytest.approx(max(result.scores.values()))
        assert sum(result.scores.values()) == pytest.approx(1.0)
        assert result.model_version == backend.model_version

    def test_all_three_labels_populated_from_id2label(self, monkeypatch) -> None:
        _inject_fake_backends(monkeypatch, [0.0, 0.0, 4.0])  # contradiction dominates
        result = TransformersNLIBackend().classify("p", "h")
        assert set(result.scores) == set(NLILabel)
        assert result.label is NLILabel.CONTRADICTION

    def test_model_is_loaded_once_then_reused(self, monkeypatch) -> None:
        _inject_fake_backends(monkeypatch, [0.0, 5.0, 0.0])  # neutral dominates
        backend = TransformersNLIBackend()
        assert backend._model is None  # lazy: nothing loaded yet
        backend.classify("p1", "h1")
        loaded = backend._model
        assert loaded is not None
        result = backend.classify("p2", "h2")
        assert backend._model is loaded  # reused, not reloaded
        assert result.label is NLILabel.NEUTRAL
