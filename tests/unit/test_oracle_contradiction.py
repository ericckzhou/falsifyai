"""Tests for falsifyai.oracles.contradiction.ContradictionOracle (PR-J)."""

from falsifyai.oracles.base import OracleContext
from falsifyai.oracles.contradiction import ContradictionOracle
from falsifyai.oracles.nli import MockNLIBackend, NLILabel
from falsifyai.spec.models import ExpectedSection
from falsifyai.verdict.models import Verdict


def _ctx(*, reference=None, outputs=("o1", "o2", "o3")) -> OracleContext:
    return OracleContext(
        original_output=outputs[0],
        perturbed_outputs=list(outputs[1:]),
        expected=ExpectedSection(reference=reference),
    )


def test_no_backend_degrades() -> None:
    v = ContradictionOracle(None).evaluate(_ctx())
    assert v.triggered is False


def test_outputs_contradicting_reference_are_consistently_wrong() -> None:
    nli = MockNLIBackend(default_label=NLILabel.CONTRADICTION)
    v = ContradictionOracle(nli).evaluate(_ctx(reference="Paris is the capital of France"))
    assert v.triggered is True
    assert v.verdict_contribution is Verdict.CONSISTENTLY_WRONG


def test_outputs_contradicting_each_other_are_ambiguous() -> None:
    # No reference -> intra-set path. All pairs contradict -> the set disagrees.
    nli = MockNLIBackend(default_label=NLILabel.CONTRADICTION)
    v = ContradictionOracle(nli).evaluate(_ctx(reference=None))
    assert v.triggered is True
    assert v.verdict_contribution is Verdict.AMBIGUOUS


def test_reference_path_takes_precedence_over_intraset() -> None:
    # Outputs contradict both the reference and each other; vs-reference wins.
    nli = MockNLIBackend(default_label=NLILabel.CONTRADICTION)
    v = ContradictionOracle(nli).evaluate(_ctx(reference="some reference"))
    assert v.verdict_contribution is Verdict.CONSISTENTLY_WRONG


def test_no_contradiction_does_not_trigger() -> None:
    nli = MockNLIBackend(default_label=NLILabel.NEUTRAL)
    v = ContradictionOracle(nli).evaluate(_ctx(reference="some reference"))
    assert v.triggered is False
    assert v.verdict_contribution is None


def test_single_output_cannot_self_contradict() -> None:
    nli = MockNLIBackend(default_label=NLILabel.CONTRADICTION)
    v = ContradictionOracle(nli).evaluate(_ctx(reference=None, outputs=("only",)))
    assert v.triggered is False
