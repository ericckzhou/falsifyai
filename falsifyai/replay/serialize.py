"""Artifact-scoped JSON serialization for ReplayArtifact.

Per PR #6 plan decision I2: this layer is intentionally narrow. It does NOT
provide a generic recursive serializer for arbitrary dataclasses. It exposes
exactly two functions:

- ``artifact_to_json(artifact) -> str``
- ``artifact_from_json(s) -> ReplayArtifact``

Encoding strategy: ``dataclasses.asdict`` walks the dataclass tree to dicts,
then ``json.dumps`` with a custom ``default`` handles the three leaf types
that aren't naturally JSON-encodable (Enums, datetimes, pydantic models).

Decoding strategy: explicit per-dataclass factory functions. No reflection,
no class registry. Each new field that lands in a persisted dataclass forces
the test author to update the corresponding ``_make_*`` here. This is
deliberate: a silent schema drift is worse than a loud one.
"""

import dataclasses
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

from falsifyai.execution.models import Execution, ModelRequest
from falsifyai.invariants.base import InvariantResult, Severity
from falsifyai.perturbation.base import (
    PerturbationCategory,
    PerturbationLineage,
    PerturbedInput,
)
from falsifyai.replay.models import (
    CaseResult,
    CliInvocation,
    PerturbedRun,
    ReplayArtifact,
    SessionVerdict,
)
from falsifyai.replay.protocol import ReplayStoreError
from falsifyai.spec.materializer import MaterializedCase, MaterializedSpec
from falsifyai.spec.models import ExpectedSection, ModelConfig, RunConfig, VerdictConfig
from falsifyai.verdict.models import Verdict

# ---------------------------------------------------------------------------
# Encode
# ---------------------------------------------------------------------------


def artifact_to_json(artifact: ReplayArtifact) -> str:
    """Serialize a ReplayArtifact to a canonical JSON string."""
    _require_tz_aware(artifact.created_at, "created_at")
    payload = dataclasses.asdict(artifact)
    return json.dumps(payload, default=_encode_leaf, sort_keys=True, separators=(",", ":"))


def _encode_leaf(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        _require_tz_aware(obj, "datetime field")
        return obj.isoformat()
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    raise TypeError(f"Cannot serialize value of type {type(obj).__name__}")


def _require_tz_aware(ts: datetime, label: str) -> None:
    if ts.tzinfo is None:
        raise ReplayStoreError(f"{label} must be timezone-aware (naive datetime rejected)")


# ---------------------------------------------------------------------------
# Decode
# ---------------------------------------------------------------------------


def artifact_from_json(s: str) -> ReplayArtifact:
    """Reconstruct a ReplayArtifact from its JSON form.

    Raises ReplayStoreError on any schema mismatch (missing field, bad type).
    """
    try:
        data = json.loads(s)
        return _make_artifact(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise ReplayStoreError(f"failed to deserialize ReplayArtifact: {exc}") from exc


def _make_artifact(d: dict[str, Any]) -> ReplayArtifact:
    return ReplayArtifact(
        session_id=d["session_id"],
        created_at=datetime.fromisoformat(d["created_at"]),
        falsifyai_version=d["falsifyai_version"],
        spec_hash=d["spec_hash"],
        materialized_hash=d["materialized_hash"],
        materialized=_make_materialized_spec(d["materialized"]),
        case_results=[_make_case_result(c) for c in d["case_results"]],
        session_verdict=_make_session_verdict(d["session_verdict"]),
        # PR-35: optional descriptive provenance. ``.get(...)`` preserves
        # backward-compat reads of pre-PR-35 artifacts (missing key -> None).
        cli_invocation=_make_cli_invocation(d.get("cli_invocation")),
    )


def _make_cli_invocation(d: dict[str, Any] | None) -> CliInvocation | None:
    """Factory for the optional cli_invocation field (PR-35).

    JSON has no tuple type, so ``argv`` round-trips as a list and must be
    re-tupled here to satisfy the ``CliInvocation`` dataclass contract.
    """
    if d is None:
        return None
    return CliInvocation(
        argv=tuple(d["argv"]),
        falsifyai_version=d["falsifyai_version"],
    )


def _make_session_verdict(d: dict[str, Any]) -> SessionVerdict:
    return SessionVerdict(
        session_verdict=Verdict(d["session_verdict"]),
        confidence=d["confidence"],
        case_count=d["case_count"],
        fragile_count=d["fragile_count"],
        consistently_wrong_count=d["consistently_wrong_count"],
        # PR #11+ field; default preserves backward-compat reads.
        falsifyai_falsifiability_score=d.get("falsifyai_falsifiability_score", 0.0),
    )


def _make_case_result(d: dict[str, Any]) -> CaseResult:
    return CaseResult(
        case_id=d["case_id"],
        original_input=d["original_input"],
        original_execution=_make_execution(d["original_execution"]),
        perturbed=[_make_perturbed_run(p) for p in d["perturbed"]],
        verdict=Verdict(d["verdict"]),
        verdict_confidence=d["verdict_confidence"],
        # PR #11+ fields; defaults preserve backward-compat reads of
        # PR #6/#8 era artifacts that didn't carry these.
        stability=d.get("stability", 0.0),
        stability_ci_low=d.get("stability_ci_low", 0.0),
        stability_ci_high=d.get("stability_ci_high", 0.0),
        per_family_stability=dict(d.get("per_family_stability", {})),
        worst_case_family=d.get("worst_case_family"),
    )


def _make_perturbed_run(d: dict[str, Any]) -> PerturbedRun:
    return PerturbedRun(
        perturbed_input=_make_perturbed_input(d["perturbed_input"]),
        execution=_make_execution(d["execution"]),
        invariant_results=[_make_invariant_result(r) for r in d["invariant_results"]],
    )


def _make_execution(d: dict[str, Any]) -> Execution:
    return Execution(
        request=_make_model_request(d["request"]),
        output_text=d["output_text"],
        latency_ms=d["latency_ms"],
        prompt_tokens=d.get("prompt_tokens"),
        completion_tokens=d.get("completion_tokens"),
        cached=d["cached"],
        seed_provided=d["seed_provided"],
    )


def _make_model_request(d: dict[str, Any]) -> ModelRequest:
    return ModelRequest(
        provider=d["provider"],
        model=d["model"],
        prompt=d["prompt"],
        temperature=d["temperature"],
        max_tokens=d["max_tokens"],
        seed=d.get("seed"),
        timeout_seconds=d["timeout_seconds"],
    )


def _make_invariant_result(d: dict[str, Any]) -> InvariantResult:
    return InvariantResult(
        invariant_name=d["invariant_name"],
        passed=d["passed"],
        score=d.get("score"),
        details=d["details"],
        severity=Severity(d["severity"]),
        evidence=d.get("evidence", {}),
    )


def _make_perturbed_input(d: dict[str, Any]) -> PerturbedInput:
    return PerturbedInput(
        text=d["text"],
        lineage=_make_perturbation_lineage(d["lineage"]),
        validity_score=d["validity_score"],
        metadata=d.get("metadata", {}),
    )


def _make_perturbation_lineage(d: dict[str, Any]) -> PerturbationLineage:
    return PerturbationLineage(
        perturbation_type=d["perturbation_type"],
        category=PerturbationCategory(d["category"]),
        method=d["method"],
        seed=d["seed"],
        params=d.get("params", {}),
        parent_input_hash=d["parent_input_hash"],
    )


def _make_materialized_spec(d: dict[str, Any]) -> MaterializedSpec:
    return MaterializedSpec(
        spec_hash=d["spec_hash"],
        materialized_hash=d["materialized_hash"],
        session_seed=d["session_seed"],
        falsifyai_version=d["falsifyai_version"],
        model=ModelConfig(**d["model"]),
        run=RunConfig(**d["run"]),
        cases=[_make_materialized_case(c) for c in d["cases"]],
    )


def _make_materialized_case(d: dict[str, Any]) -> MaterializedCase:
    return MaterializedCase(
        case_id=d["case_id"],
        case_seed=d["case_seed"],
        original_input=d["original_input"],
        realized_perturbations=[_make_perturbed_input(p) for p in d["realized_perturbations"]],
        tags=list(d.get("tags", [])),
        expected=ExpectedSection(**d["expected"]),
        verdict_config=VerdictConfig(**d["verdict_config"]),
    )
