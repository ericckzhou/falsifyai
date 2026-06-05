"""Tests for falsifyai.oracles.meta.MetaOracle."""

from falsifyai.invariants.base import InvariantResult, Severity
from falsifyai.oracles.base import OracleContext, OracleVerdict
from falsifyai.oracles.consistency import ConsistencyOracle
from falsifyai.oracles.contradiction import ContradictionOracle
from falsifyai.oracles.meta import MetaOracle
from falsifyai.oracles.nli import MockNLIBackend, NLILabel
from falsifyai.spec.models import ExpectedSection
from falsifyai.verdict.models import Verdict


def _result(name: str, passed: bool) -> InvariantResult:
    return InvariantResult(
        invariant_name=name, passed=passed, score=None, details="", severity=Severity.HIGH
    )


def _ctx(*, invariant_results=None, peer_verdicts=None) -> OracleContext:
    return OracleContext(
        original_output="x",
        perturbed_outputs=["x"],
        expected=ExpectedSection(),
        invariant_results=invariant_results or [],
        peer_verdicts=peer_verdicts or [],
    )


def _peer(name: str, triggered: bool, contribution, confidence: float) -> OracleVerdict:
    return OracleVerdict(
        oracle_name=name,
        triggered=triggered,
        verdict_contribution=contribution,
        confidence=confidence,
        reasoning="",
    )


# --- invariant degeneration --------------------------------------------------


def test_invariant_failing_baseline_and_all_is_degenerate() -> None:
    """An invariant that fails on every output including baseline -> INVALID_EVAL."""
    matrix = [[_result("contains", passed=False)] for _ in range(6)]  # baseline + 5
    v = MetaOracle().evaluate(_ctx(invariant_results=matrix))
    assert v.triggered is True
    assert v.verdict_contribution is Verdict.INVALID_EVAL
    assert v.confidence == 1.0


def test_invariant_passing_baseline_is_not_degenerate() -> None:
    """Fails on perturbations but passes the baseline -> not malformed (FRAGILE-ish)."""
    matrix = [[_result("contains", passed=True)]]  # baseline passes
    matrix += [[_result("contains", passed=False)] for _ in range(5)]  # 5/6 = 83% < 95%
    v = MetaOracle().evaluate(_ctx(invariant_results=matrix))
    assert v.triggered is False
    assert v.verdict_contribution is None


def test_degeneration_suppressed_when_peer_oracle_triggered() -> None:
    """A consistently-wrong model is explained by a primary oracle, not a broken eval."""
    matrix = [[_result("contains", passed=False)] for _ in range(6)]
    consistency = _peer("consistency", True, Verdict.CONSISTENTLY_WRONG, 1.0)
    v = MetaOracle().evaluate(_ctx(invariant_results=matrix, peer_verdicts=[consistency]))
    assert v.triggered is False


def test_empty_matrix_does_not_trigger() -> None:
    v = MetaOracle().evaluate(_ctx(invariant_results=[]))
    assert v.triggered is False


def test_worst_invariant_is_reported() -> None:
    """With two invariants, the degenerate one is named."""
    matrix = [[_result("good", passed=True), _result("bad", passed=False)] for _ in range(6)]
    v = MetaOracle().evaluate(_ctx(invariant_results=matrix))
    assert v.triggered is True
    assert "bad" in v.reasoning


# --- oracle conflict ---------------------------------------------------------


def test_high_confidence_conflict_triggers() -> None:
    a = _peer("consistency", True, Verdict.CONSISTENTLY_WRONG, 0.95)
    b = _peer("contradiction", True, Verdict.FRAGILE, 0.9)
    v = MetaOracle().evaluate(_ctx(peer_verdicts=[a, b]))
    assert v.triggered is True
    assert v.verdict_contribution is Verdict.INVALID_EVAL
    assert "conflict" in v.reasoning.lower()


def test_agreeing_oracles_do_not_conflict() -> None:
    a = _peer("consistency", True, Verdict.CONSISTENTLY_WRONG, 0.95)
    b = _peer("other", True, Verdict.CONSISTENTLY_WRONG, 0.9)
    v = MetaOracle().evaluate(_ctx(peer_verdicts=[a, b]))
    assert v.triggered is False


def test_low_confidence_disagreement_is_not_a_conflict() -> None:
    a = _peer("consistency", True, Verdict.CONSISTENTLY_WRONG, 0.6)
    b = _peer("contradiction", True, Verdict.FRAGILE, 0.5)
    v = MetaOracle().evaluate(_ctx(peer_verdicts=[a, b]))
    assert v.triggered is False


def test_single_oracle_never_conflicts() -> None:
    a = _peer("consistency", True, Verdict.CONSISTENTLY_WRONG, 1.0)
    v = MetaOracle().evaluate(_ctx(peer_verdicts=[a]))
    assert v.triggered is False


def test_clean_eval_does_not_trigger() -> None:
    matrix = [[_result("contains", passed=True)] for _ in range(6)]
    v = MetaOracle().evaluate(_ctx(invariant_results=matrix))
    assert v.triggered is False
    assert v.oracle_name == "meta"


# --- conflict via REAL oracles (PR-J: now reachable) -------------------------


def test_real_consistency_vs_contradiction_conflict_is_detected() -> None:
    """PR-J makes the oracle-conflict path live for the first time.

    Before PR-J only ConsistencyOracle existed as a primary peer, so the
    meta-oracle's conflict detector (needs >= 2 disagreeing high-confidence
    oracles) could never fire. With ContradictionOracle as a second NLI-driven
    peer, a set that ConsistencyOracle reads as CONSISTENTLY_WRONG (agrees on a
    known-wrong answer) while ContradictionOracle reads as AMBIGUOUS (the outputs
    contradict each other) is a genuine, mutually-exclusive conflict -> INVALID_EVAL.
    """
    # Ground truth requires "Paris"; every output says "London" -> ConsistencyOracle
    # ground-truth path triggers CONSISTENTLY_WRONG at confidence 1.0.
    oracle_ctx = OracleContext(
        original_output="London",
        perturbed_outputs=["London", "London"],
        expected=ExpectedSection(contains=["Paris"]),
    )
    consistency = ConsistencyOracle().evaluate(oracle_ctx)
    assert consistency.verdict_contribution is Verdict.CONSISTENTLY_WRONG

    # No reference -> ContradictionOracle takes the intra-set path; mock forces
    # every pair to contradict -> AMBIGUOUS at confidence 1.0.
    contradiction = ContradictionOracle(
        MockNLIBackend(default_label=NLILabel.CONTRADICTION)
    ).evaluate(oracle_ctx)
    assert contradiction.verdict_contribution is Verdict.AMBIGUOUS

    meta = MetaOracle().evaluate(_ctx(peer_verdicts=[consistency, contradiction]))
    assert meta.triggered is True
    assert meta.verdict_contribution is Verdict.INVALID_EVAL
    assert "conflict" in meta.reasoning.lower()
