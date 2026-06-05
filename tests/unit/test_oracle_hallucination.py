"""Tests for falsifyai.oracles.hallucination.HallucinationOracle (PR-J).

Regression note: 0.6.0 folded NLI NEUTRAL into "unsupported -> CONSISTENTLY_WRONG",
flagging correct *paraphrased* outputs as the framework's most severe verdict
(probe-03, case ``cancellation_deadline_inversion``). The oracle now reserves
CONSISTENTLY_WRONG for genuine CONTRADICTION; NEUTRAL abstains.
"""

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
    nli = MockNLIBackend(default_label=NLILabel.CONTRADICTION)
    v = HallucinationOracle(nli).evaluate(_ctx(reference=None))
    assert v.triggered is False


def test_contradicting_outputs_trigger_consistently_wrong() -> None:
    nli = MockNLIBackend(default_label=NLILabel.CONTRADICTION)
    v = HallucinationOracle(nli).evaluate(_ctx(reference="the earth orbits the sun"))
    assert v.triggered is True
    assert v.verdict_contribution is Verdict.CONSISTENTLY_WRONG


def test_neutral_outputs_abstain() -> None:
    # NEUTRAL = grounding unconfirmed, NOT wrong. The oracle must not fire.
    nli = MockNLIBackend(default_label=NLILabel.NEUTRAL)
    v = HallucinationOracle(nli).evaluate(_ctx(reference="the earth orbits the sun"))
    assert v.triggered is False
    assert v.verdict_contribution is None


def test_entailed_outputs_are_supported() -> None:
    nli = MockNLIBackend(default_label=NLILabel.ENTAILMENT)
    v = HallucinationOracle(nli).evaluate(_ctx(reference="the earth orbits the sun"))
    assert v.triggered is False
    assert v.verdict_contribution is None


def test_probe03_correct_paraphrase_does_not_hallucinate() -> None:
    """Regression: probe-03 cancellation_deadline_inversion.

    Outputs are CORRECT paraphrases of the reference; a sentence-pair NLI head
    labels them NEUTRAL (not ENTAILMENT). The oracle must abstain, not report
    CONSISTENTLY_WRONG at confidence 1.00 as 0.6.0 did.
    """
    reference = (
        "To avoid the renewal charge, a customer must cancel at least 14 days "
        "before the renewal date."
    )
    outputs = (
        "According to the policy, a customer must cancel at least 14 days before "
        "the renewal date to avoid the charge.",
        "To avoid being charged, customers need to cancel at least 14 days before "
        "the renewal date, since subscriptions auto-renew otherwise.",
    )
    nli = MockNLIBackend(default_label=NLILabel.NEUTRAL)
    v = HallucinationOracle(nli).evaluate(_ctx(reference=reference, outputs=outputs))
    assert v.triggered is False
    assert v.verdict_contribution is None
