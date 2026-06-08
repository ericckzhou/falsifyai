"""Unit tests for ``CliInvocation`` and the ``ReplayArtifact.cli_invocation`` field (PR-35).

Exercises ``CliInvocation`` from ``falsifyai.replay.models`` and the
``ReplayArtifact.cli_invocation`` field.

Capture contract (per PR-35 plan §1):
- ``CliInvocation`` is a frozen dataclass with exactly two fields:
  ``argv: tuple[str, ...]`` and ``falsifyai_version: str``
- ``ReplayArtifact.cli_invocation`` is optional and defaults to ``None``;
  pre-PR-35 artifacts (and artifacts produced by read-only consumer commands)
  carry ``cli_invocation = None``.

Semantic boundary: ``cli_invocation`` is descriptive provenance — it records
what command produced the artifact, not a determinism guarantee.
"""

import dataclasses

import pytest

from falsifyai.replay.models import CliInvocation, ReplayArtifact
from tests.fixtures.build_artifact import make_artifact

# ---------------------------------------------------------------------------
# CliInvocation: shape, fields, immutability
# ---------------------------------------------------------------------------


def test_cli_invocation_is_frozen_dataclass() -> None:
    assert dataclasses.is_dataclass(CliInvocation)
    inv = CliInvocation(argv=("falsifyai", "run", "spec.yaml"), falsifyai_version="0.3.0")
    with pytest.raises(dataclasses.FrozenInstanceError):
        inv.argv = ()  # type: ignore[misc]


def test_cli_invocation_has_exactly_two_fields() -> None:
    """The capture contract is narrow by design — no env, no cwd, no identity."""
    field_names = {f.name for f in dataclasses.fields(CliInvocation)}
    assert field_names == {"argv", "falsifyai_version"}


def test_cli_invocation_argv_is_tuple_of_strings() -> None:
    inv = CliInvocation(
        argv=("falsifyai", "run", "spec.yaml", "--store-path", ":memory:"),
        falsifyai_version="0.3.0",
    )
    assert isinstance(inv.argv, tuple)
    assert all(isinstance(tok, str) for tok in inv.argv)


def test_cli_invocation_equality_by_value() -> None:
    a = CliInvocation(argv=("falsifyai", "run", "spec.yaml"), falsifyai_version="0.3.0")
    b = CliInvocation(argv=("falsifyai", "run", "spec.yaml"), falsifyai_version="0.3.0")
    c = CliInvocation(argv=("falsifyai", "run", "other.yaml"), falsifyai_version="0.3.0")
    d = CliInvocation(argv=("falsifyai", "run", "spec.yaml"), falsifyai_version="0.4.0")
    assert a == b
    assert a != c
    assert a != d


def test_cli_invocation_replace_works() -> None:
    """``dataclasses.replace`` should work — needed by serialization roundtrip helpers."""
    original = CliInvocation(argv=("falsifyai", "run", "a"), falsifyai_version="0.3.0")
    bumped = dataclasses.replace(original, falsifyai_version="0.4.0")
    assert bumped.argv == ("falsifyai", "run", "a")
    assert bumped.falsifyai_version == "0.4.0"


# ---------------------------------------------------------------------------
# ReplayArtifact.cli_invocation: optional field, default None
# ---------------------------------------------------------------------------


def test_replay_artifact_cli_invocation_field_exists() -> None:
    field_names = {f.name for f in dataclasses.fields(ReplayArtifact)}
    assert "cli_invocation" in field_names


def test_replay_artifact_cli_invocation_defaults_to_none() -> None:
    """Backward compat for pre-PR-35 artifacts: missing field → None."""
    artifact = make_artifact()
    assert artifact.cli_invocation is None


def test_replay_artifact_accepts_populated_cli_invocation() -> None:
    """Build a CliInvocation, attach to an artifact, confirm it survives."""
    inv = CliInvocation(
        argv=("falsifyai", "run", "spec.yaml", "--store-path", ":memory:"),
        falsifyai_version="0.3.0",
    )
    base = make_artifact()
    artifact = dataclasses.replace(base, cli_invocation=inv)
    assert artifact.cli_invocation is inv
    assert artifact.cli_invocation.argv[0] == "falsifyai"


def test_existing_fixtures_still_work_without_cli_invocation() -> None:
    """The build_artifact fixture must not require cli_invocation — default None preserves
    backward compatibility for all 7+ test files that already use it.
    """
    artifact = make_artifact()
    # Nothing else about the artifact should change; only the new field exists with None.
    assert artifact.session_id == "11111111-1111-1111-1111-111111111111"
    assert artifact.cli_invocation is None
