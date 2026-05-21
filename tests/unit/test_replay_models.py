"""Tests for falsifyai.replay.models — the persisted replay artifact shape.

These tests cover the *shape* of the dataclasses (frozen, equality, field
presence). Serialization round-trips are covered by test_replay_serialize.py;
end-to-end store contract is covered by test_replay_store_contract.py.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from falsifyai.execution.models import Execution, ModelRequest
from falsifyai.invariants.base import InvariantResult, Severity
from falsifyai.perturbation.base import (
    PerturbationCategory,
    PerturbationLineage,
    PerturbedInput,
    hash_input,
)
from falsifyai.replay.models import (
    CaseResult,
    PerturbedRun,
    ReplayArtifact,
    SessionVerdict,
)
from falsifyai.spec.materializer import MaterializedSpec
from falsifyai.spec.models import ModelConfig, RunConfig
from falsifyai.verdict.models import Verdict


def _make_execution(prompt: str = "ping", output: str = "pong") -> Execution:
    req = ModelRequest(
        provider="mock",
        model="mock-model",
        prompt=prompt,
        temperature=0.0,
        max_tokens=128,
        seed=42,
        timeout_seconds=30,
    )
    return Execution(
        request=req,
        output_text=output,
        latency_ms=1.0,
        prompt_tokens=1,
        completion_tokens=1,
        cached=False,
        seed_provided=True,
    )


def _make_perturbed_input(text: str = "p1ng") -> PerturbedInput:
    lineage = PerturbationLineage(
        perturbation_type="typo_noise",
        category=PerturbationCategory.LEXICAL,
        method="substitute",
        seed=1,
        params={"sample_index": 0},
        parent_input_hash=hash_input("ping"),
    )
    return PerturbedInput(text=text, lineage=lineage, validity_score=1.0)


def _make_invariant_result() -> InvariantResult:
    return InvariantResult(
        invariant_name="contains",
        passed=True,
        score=1.0,
        details="all values present",
        severity=Severity.HIGH,
        evidence={"missing": []},
    )


def _make_perturbed_run() -> PerturbedRun:
    return PerturbedRun(
        perturbed_input=_make_perturbed_input(),
        execution=_make_execution(prompt="p1ng", output="pong"),
        invariant_results=[_make_invariant_result()],
    )


def _make_case_result(case_id: str = "case-a", verdict: Verdict = Verdict.STABLE) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        original_input="ping",
        original_execution=_make_execution(),
        perturbed=[_make_perturbed_run()],
        verdict=verdict,
        verdict_confidence=0.9,
    )


def _make_session_verdict(verdict: Verdict = Verdict.STABLE) -> SessionVerdict:
    return SessionVerdict(
        session_verdict=verdict,
        confidence=0.9,
        case_count=1,
        fragile_count=0,
        consistently_wrong_count=0,
    )


def _make_materialized_spec() -> MaterializedSpec:
    return MaterializedSpec(
        spec_hash="abc123",
        materialized_hash="def456",
        session_seed=42,
        falsifyai_version="0.0.1",
        model=ModelConfig(provider="mock", model="mock-model"),
        run=RunConfig(seed=42),
        cases=[],
    )


def _make_artifact() -> ReplayArtifact:
    return ReplayArtifact(
        session_id="sess-xyz",
        created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=UTC),
        falsifyai_version="0.0.1",
        spec_hash="abc123",
        materialized_hash="def456",
        materialized=_make_materialized_spec(),
        case_results=[_make_case_result()],
        session_verdict=_make_session_verdict(),
    )


# ---------------------------------------------------------------------------
# Frozen semantics
# ---------------------------------------------------------------------------


def test_perturbed_run_is_frozen() -> None:
    run = _make_perturbed_run()
    with pytest.raises(FrozenInstanceError):
        run.perturbed_input = _make_perturbed_input("xxx")  # type: ignore[misc]


def test_case_result_is_frozen() -> None:
    cr = _make_case_result()
    with pytest.raises(FrozenInstanceError):
        cr.verdict = Verdict.FRAGILE  # type: ignore[misc]


def test_session_verdict_is_frozen() -> None:
    sv = _make_session_verdict()
    with pytest.raises(FrozenInstanceError):
        sv.confidence = 0.5  # type: ignore[misc]


def test_replay_artifact_is_frozen() -> None:
    artifact = _make_artifact()
    with pytest.raises(FrozenInstanceError):
        artifact.session_id = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Construction + field access
# ---------------------------------------------------------------------------


def test_replay_artifact_construction_with_realistic_nested_data() -> None:
    artifact = _make_artifact()

    assert artifact.session_id == "sess-xyz"
    assert artifact.spec_hash == "abc123"
    assert artifact.materialized_hash == "def456"
    assert artifact.created_at.tzinfo is UTC

    # nested case result
    assert len(artifact.case_results) == 1
    case = artifact.case_results[0]
    assert case.case_id == "case-a"
    assert case.verdict is Verdict.STABLE

    # nested perturbed run
    assert len(case.perturbed) == 1
    run = case.perturbed[0]
    assert run.perturbed_input.text == "p1ng"
    assert run.execution.output_text == "pong"
    assert run.invariant_results[0].invariant_name == "contains"


def test_session_verdict_holds_counts() -> None:
    sv = SessionVerdict(
        session_verdict=Verdict.FRAGILE,
        confidence=0.7,
        case_count=10,
        fragile_count=3,
        consistently_wrong_count=1,
    )
    assert sv.session_verdict is Verdict.FRAGILE
    assert sv.case_count == 10
    assert sv.fragile_count == 3
    assert sv.consistently_wrong_count == 1


# ---------------------------------------------------------------------------
# Equality semantics (frozen dataclass auto-eq)
# ---------------------------------------------------------------------------


def test_replay_artifact_equality_by_value() -> None:
    """Two artifacts built from identical components compare equal."""
    a1 = _make_artifact()
    a2 = _make_artifact()
    assert a1 == a2


def test_replay_artifact_inequality_on_session_id() -> None:
    a1 = _make_artifact()
    a2 = ReplayArtifact(
        session_id="different",
        created_at=a1.created_at,
        falsifyai_version=a1.falsifyai_version,
        spec_hash=a1.spec_hash,
        materialized_hash=a1.materialized_hash,
        materialized=a1.materialized,
        case_results=a1.case_results,
        session_verdict=a1.session_verdict,
    )
    assert a1 != a2
