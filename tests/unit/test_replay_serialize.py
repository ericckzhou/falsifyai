"""Tests for falsifyai.replay.serialize.

Scope is intentionally narrow: round-trip the full ReplayArtifact via JSON.
We do NOT test serialization of every dataclass in the codebase separately —
the serializer is artifact-scoped (per PR #6 plan, decision I2). If a future
PR needs to serialize something else, it gets its own surface.
"""

from datetime import UTC, datetime

import pytest

from falsifyai.invariants.base import Severity
from falsifyai.replay.protocol import ReplayStoreError
from falsifyai.replay.serialize import artifact_from_json, artifact_to_json
from falsifyai.verdict.models import Verdict
from tests.fixtures.build_artifact import make_artifact


def test_round_trip_preserves_semantic_equality() -> None:
    """save -> load -> equal. Per PR #6 plan, byte-identical second-save is out of scope."""
    original = make_artifact()
    encoded = artifact_to_json(original)
    restored = artifact_from_json(encoded)
    assert restored == original


def test_round_trip_preserves_nested_executions_and_invariants() -> None:
    """Verify the deep structure survives — perturbed runs, executions, invariant results."""
    original = make_artifact()
    restored = artifact_from_json(artifact_to_json(original))

    case = restored.case_results[0]
    assert case.original_execution == original.case_results[0].original_execution
    assert len(case.perturbed) == 2

    typo_run = case.perturbed[0]
    assert typo_run.perturbed_input.text == "What is the captial of France?"
    assert typo_run.perturbed_input.lineage.perturbation_type == "typo_noise"
    assert typo_run.perturbed_input.lineage.params["sample_index"] == 0
    assert typo_run.execution.cached is False
    assert typo_run.invariant_results[1].invariant_name == "semantic_equivalence"
    assert typo_run.invariant_results[1].score == pytest.approx(0.97)


def test_severity_enum_round_trips() -> None:
    original = make_artifact()
    restored = artifact_from_json(artifact_to_json(original))
    inv = restored.case_results[0].perturbed[0].invariant_results[0]
    assert isinstance(inv.severity, Severity)
    assert inv.severity is Severity.HIGH


def test_verdict_enum_round_trips() -> None:
    for v in (Verdict.STABLE, Verdict.FRAGILE, Verdict.CONSISTENTLY_WRONG):
        original = make_artifact(verdict=v)
        restored = artifact_from_json(artifact_to_json(original))
        assert restored.session_verdict.session_verdict is v
        assert restored.case_results[0].verdict is v


def test_datetime_round_trips_as_iso_utc() -> None:
    ts = datetime(2026, 5, 21, 14, 30, 45, 123456, tzinfo=UTC)
    original = make_artifact(created_at=ts)
    encoded = artifact_to_json(original)
    assert "2026-05-21T14:30:45" in encoded  # ISO-8601 surface
    restored = artifact_from_json(encoded)
    assert restored.created_at == ts
    assert restored.created_at.tzinfo is not None


def test_naive_datetime_on_input_raises() -> None:
    naive = datetime(2026, 5, 21, 14, 30, 0)  # no tzinfo
    bad = make_artifact(created_at=naive)
    with pytest.raises(ReplayStoreError, match="naive"):
        artifact_to_json(bad)


def test_missing_critical_field_on_deserialization_raises() -> None:
    """Removing a required top-level field from the JSON should error loudly."""
    original = make_artifact()
    encoded = artifact_to_json(original)
    import json

    payload = json.loads(encoded)
    del payload["spec_hash"]
    corrupted = json.dumps(payload)
    with pytest.raises(ReplayStoreError):
        artifact_from_json(corrupted)
