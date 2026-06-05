"""Tests for falsifyai.oracles.grounding.GroundingOracle (PR-J)."""

from falsifyai.oracles.base import OracleContext
from falsifyai.oracles.grounding import GroundingOracle
from falsifyai.oracles.nli import MockNLIBackend, NLILabel
from falsifyai.spec.models import ExpectedSection
from falsifyai.verdict.models import Verdict


def _ctx(*, reference=None, context_text=None, outputs=("o1", "o2")) -> OracleContext:
    return OracleContext(
        original_output=outputs[0],
        perturbed_outputs=list(outputs[1:]),
        expected=ExpectedSection(reference=reference),
        context_text=context_text,
    )


def test_no_backend_degrades() -> None:
    v = GroundingOracle(None).evaluate(_ctx(reference="the sky is blue"))
    assert v.triggered is False
    assert v.verdict_contribution is None


def test_no_source_degrades() -> None:
    nli = MockNLIBackend(default_label=NLILabel.ENTAILMENT)
    v = GroundingOracle(nli).evaluate(_ctx(reference=None, context_text=None))
    assert v.triggered is False


def test_entailed_outputs_are_grounded() -> None:
    nli = MockNLIBackend(default_label=NLILabel.ENTAILMENT)
    v = GroundingOracle(nli).evaluate(_ctx(reference="the capital of France is Paris"))
    assert v.triggered is True
    assert v.verdict_contribution is Verdict.INFORMATION_PRESENT
    assert v.confidence == 1.0


def test_unentailed_outputs_are_not_grounded() -> None:
    nli = MockNLIBackend(default_label=NLILabel.NEUTRAL)
    v = GroundingOracle(nli).evaluate(_ctx(reference="the capital of France is Paris"))
    assert v.triggered is False
    assert v.verdict_contribution is None


def test_context_text_preferred_over_reference() -> None:
    # Entail against the retrieved context, contradict the (stale) reference.
    nli = MockNLIBackend(
        rules={
            ("CTX", "o1"): NLILabel.ENTAILMENT,
            ("CTX", "o2"): NLILabel.ENTAILMENT,
            ("REF", "o1"): NLILabel.CONTRADICTION,
            ("REF", "o2"): NLILabel.CONTRADICTION,
        }
    )
    v = GroundingOracle(nli).evaluate(_ctx(reference="REF", context_text="CTX"))
    assert v.triggered is True  # used context (entailed), not reference (contradicted)
    assert v.verdict_contribution is Verdict.INFORMATION_PRESENT
