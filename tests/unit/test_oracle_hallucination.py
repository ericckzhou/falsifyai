"""Tests for falsifyai.oracles.hallucination.HallucinationOracle (PR-J)."""

from falsifyai.oracles.base import OracleContext
from falsifyai.oracles.hallucination import HallucinationOracle
from falsifyai.oracles.nli import MockNLIBackend, NLILabel
from falsifyai.spec.models import ExpectedSection
from falsifyai.verdict.models import Verdict


def _ctx(*, reference=None, outputs=("o1", "o2")) -> OracleContext:
    return OracleContext(
        original_output=outputs[0],
        perturbed_outputs=list(outputs[1:]),
        expected=ExpectedSection(reference=reference),
    )


def test_no_backend_degrades() -> None:
    v = HallucinationOracle(None).evaluate(_ctx(reference="r"))
    assert v.triggered is False


def test_no_reference_degrades() -> None:
    nli = MockNLIBackend(default_label=NLILabel.NEUTRAL)
    v = HallucinationOracle(nli).evaluate(_ctx(reference=None))
    assert v.triggered is False


def test_unsupported_outputs_trigger_consistently_wrong() -> None:
    nli = MockNLIBackend(default_label=NLILabel.NEUTRAL)
    v = HallucinationOracle(nli).evaluate(_ctx(reference="the earth orbits the sun"))
    assert v.triggered is True
    assert v.verdict_contribution is Verdict.CONSISTENTLY_WRONG


def test_contradicting_outputs_also_count_as_unsupported() -> None:
    nli = MockNLIBackend(default_label=NLILabel.CONTRADICTION)
    v = HallucinationOracle(nli).evaluate(_ctx(reference="the earth orbits the sun"))
    assert v.triggered is True
    assert v.verdict_contribution is Verdict.CONSISTENTLY_WRONG


def test_entailed_outputs_are_supported() -> None:
    nli = MockNLIBackend(default_label=NLILabel.ENTAILMENT)
    v = HallucinationOracle(nli).evaluate(_ctx(reference="the earth orbits the sun"))
    assert v.triggered is False
    assert v.verdict_contribution is None
