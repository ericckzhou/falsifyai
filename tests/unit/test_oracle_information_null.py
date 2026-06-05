"""Tests for falsifyai.oracles.information_null.InformationNullOracle (PR-K)."""

from falsifyai.oracles.base import OracleContext
from falsifyai.oracles.information_null import InformationNullOracle
from falsifyai.spec.models import ExpectedSection
from falsifyai.verdict.models import Verdict


def _ctx(outputs: list[str]) -> OracleContext:
    return OracleContext(
        original_output=outputs[0],
        perturbed_outputs=outputs[1:],
        expected=ExpectedSection(),
    )


def test_refusals_trigger_information_null() -> None:
    v = InformationNullOracle().evaluate(
        _ctx(["I cannot help with that.", "I can't help with that.", "I am unable to assist."])
    )
    assert v.triggered is True
    assert v.verdict_contribution is Verdict.INFORMATION_NULL


def test_empty_outputs_trigger() -> None:
    v = InformationNullOracle().evaluate(_ctx(["", "   ", "\n"]))
    assert v.triggered is True


def test_hedging_triggers() -> None:
    v = InformationNullOracle().evaluate(
        _ctx(["It depends on the context.", "Hard to say, really.", "It's unclear."])
    )
    assert v.triggered is True


def test_substantive_answer_does_not_trigger() -> None:
    # Terse but real answers must NOT be flagged as null.
    v = InformationNullOracle().evaluate(_ctx(["Paris.", "Paris", "The capital is Paris."]))
    assert v.triggered is False
    assert v.verdict_contribution is None


def test_minority_refusals_do_not_trigger() -> None:
    # 1 of 3 is a refusal -> below the 50% support floor.
    v = InformationNullOracle().evaluate(_ctx(["Paris.", "Paris.", "I cannot help."]))
    assert v.triggered is False
