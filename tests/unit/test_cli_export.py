"""Unit tests for ``falsifyai.cli.export`` (PR-32, Phase C).

Tests the CLI orchestration: argument parsing, integrity gate behavior,
overwrite semantics, exit codes (0 / 3 / 7), and the rendered output.

A ``_FakeStore`` mirrors the pattern from ``test_cli_verify.py`` so we
can serve hand-constructed artifacts including intentional corruption.

The architectural assertion ``test_export_does_not_import_resolver`` is
co-located here (matches PR-31 convention).
"""

import argparse
import dataclasses
import json
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

import falsifyai.cli.export as cli_export
from falsifyai.cli.errors import InfrastructureError
from falsifyai.replay.models import ReplayArtifact
from falsifyai.replay.protocol import SessionNotFoundError
from falsifyai.spec.materializer import compute_materialized_hash
from tests.fixtures.build_artifact import make_artifact

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_artifact(session_id: str = "11111111-1111-1111-1111-111111111111") -> ReplayArtifact:
    a = make_artifact(session_id=session_id)
    correct = compute_materialized_hash(a.materialized.cases)
    return dataclasses.replace(
        a,
        materialized_hash=correct,
        materialized=dataclasses.replace(a.materialized, materialized_hash=correct),
    )


class _FakeStore:
    """Minimal ReplayStore stand-in (mirrors test_cli_verify.py)."""

    def __init__(self, artifacts: list[ReplayArtifact] | None = None) -> None:
        self._artifacts: dict[str, ReplayArtifact] = {a.session_id: a for a in (artifacts or [])}

    def load_session(self, session_id: str) -> ReplayArtifact:
        if session_id not in self._artifacts:
            raise SessionNotFoundError(session_id)
        return self._artifacts[session_id]

    def query_sessions(self, **_kwargs) -> Iterator[ReplayArtifact]:
        yield from sorted(self._artifacts.values(), key=lambda x: x.created_at, reverse=True)


def _args(
    session_id: str | None = "11111111-1111-1111-1111-111111111111",
    bundle: str | None = None,
    *,
    spec_path: str | None = None,
    allow_corrupted: bool = False,
    overwrite: bool = False,
    exported_at: str | None = "2026-05-24T12:00:00+00:00",
    store_path: str = ":memory:",
) -> argparse.Namespace:
    return argparse.Namespace(
        session_id=session_id,
        bundle=bundle,
        spec_path=spec_path,
        allow_corrupted=allow_corrupted,
        overwrite=overwrite,
        exported_at=exported_at,
        store_path=store_path,
    )


def _patch_store(monkeypatch, store: _FakeStore) -> _FakeStore:
    monkeypatch.setattr(cli_export, "_build_store", lambda _p: store)
    return store


def _read_manifest(bundle_path: Path) -> dict:
    with zipfile.ZipFile(bundle_path, "r") as zf:
        return json.loads(zf.read("manifest.json").decode("utf-8"))


# ---------------------------------------------------------------------------
# (a) Clean artifact → exit 0, bundle exists, manifest valid
# ---------------------------------------------------------------------------


def test_clean_artifact_writes_bundle_and_returns_exit_0(tmp_path, monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([_clean_artifact()]))
    bundle_path = tmp_path / "out.fai.zip"
    rc = cli_export.cmd_export(_args(bundle=str(bundle_path)))
    assert rc == 0
    assert bundle_path.exists()
    m = _read_manifest(bundle_path)
    assert m["session_id"] == "11111111-1111-1111-1111-111111111111"
    assert m["bundle_type"] == "falsifyai-replay-bundle"


# ---------------------------------------------------------------------------
# (b) Corrupted artifact → exit 7, no bundle written
# ---------------------------------------------------------------------------


def test_corrupted_artifact_returns_exit_7_and_writes_no_bundle(tmp_path, monkeypatch) -> None:
    a = _clean_artifact()
    bad = dataclasses.replace(a, materialized_hash="0" * 64)
    _patch_store(monkeypatch, _FakeStore([bad]))
    bundle_path = tmp_path / "out.fai.zip"
    rc = cli_export.cmd_export(_args(bundle=str(bundle_path)))
    assert rc == 7
    assert not bundle_path.exists()


# ---------------------------------------------------------------------------
# (c) Corrupted artifact + --allow-corrupted → exit 0 + manifest predicate set
# ---------------------------------------------------------------------------


def test_allow_corrupted_writes_bundle_and_sets_predicate(tmp_path, monkeypatch) -> None:
    a = _clean_artifact()
    bad = dataclasses.replace(a, materialized_hash="0" * 64)
    _patch_store(monkeypatch, _FakeStore([bad]))
    bundle_path = tmp_path / "out.fai.zip"
    rc = cli_export.cmd_export(_args(bundle=str(bundle_path), allow_corrupted=True))
    assert rc == 0
    assert bundle_path.exists()
    m = _read_manifest(bundle_path)
    assert m["exported_under_protest"] is True
    assert m["pre_export_integrity"]["status"] == "failed"
    assert "materialized_hash" in m["pre_export_integrity"]["failed_checks"]
    assert m["integrity_scope"]["artifact_verified"] is False
    assert m["integrity_scope"]["bundle_verified"] is True


# ---------------------------------------------------------------------------
# (d) Session not found → exit 3 (InfrastructureError)
# ---------------------------------------------------------------------------


def test_session_not_found_raises_infrastructure_error(tmp_path, monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([]))
    bundle_path = tmp_path / "out.fai.zip"
    with pytest.raises(InfrastructureError) as excinfo:
        cli_export.cmd_export(_args(session_id="missing", bundle=str(bundle_path)))
    assert excinfo.value.exit_code == 3
    assert "missing" in str(excinfo.value).lower() or "not found" in str(excinfo.value).lower()


# ---------------------------------------------------------------------------
# (e) Unwritable output path (parent dir does not exist) → exit 3 with clear msg
# ---------------------------------------------------------------------------


def test_missing_parent_directory_raises_infrastructure_error(tmp_path, monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([_clean_artifact()]))
    bundle_path = tmp_path / "nonexistent_dir" / "out.fai.zip"
    with pytest.raises(InfrastructureError) as excinfo:
        cli_export.cmd_export(_args(bundle=str(bundle_path)))
    assert excinfo.value.exit_code == 3
    msg = str(excinfo.value).lower()
    assert "parent" in msg or "does not exist" in msg or "directory" in msg


# ---------------------------------------------------------------------------
# (f) spec-path supplied → bundle includes spec.yaml byte-identically
# ---------------------------------------------------------------------------


def test_spec_path_supplied_includes_spec_yaml(tmp_path, monkeypatch) -> None:
    spec_path = tmp_path / "src.yaml"
    spec_bytes = b"falsify:\n  version: '1.0'\n  name: 'test-spec'\n"
    spec_path.write_bytes(spec_bytes)

    _patch_store(monkeypatch, _FakeStore([_clean_artifact()]))
    bundle_path = tmp_path / "out.fai.zip"
    rc = cli_export.cmd_export(_args(bundle=str(bundle_path), spec_path=str(spec_path)))
    assert rc == 0
    with zipfile.ZipFile(bundle_path, "r") as zf:
        assert "spec.yaml" in zf.namelist()
        assert zf.read("spec.yaml") == spec_bytes


# ---------------------------------------------------------------------------
# (g) spec-path omitted → no spec.yaml in bundle, README notes absence
# ---------------------------------------------------------------------------


def test_spec_path_omitted_means_no_spec_in_bundle(tmp_path, monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([_clean_artifact()]))
    bundle_path = tmp_path / "out.fai.zip"
    rc = cli_export.cmd_export(_args(bundle=str(bundle_path)))
    assert rc == 0
    with zipfile.ZipFile(bundle_path, "r") as zf:
        assert "spec.yaml" not in zf.namelist()
        readme = zf.read("README.md").decode("utf-8").lower()
        assert "no source spec" in readme or "spec_yaml: not_supplied" in readme


# ---------------------------------------------------------------------------
# (h) Existing output path → exit 3 by default
# ---------------------------------------------------------------------------


def test_existing_output_refuses_overwrite_by_default(tmp_path, monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([_clean_artifact()]))
    bundle_path = tmp_path / "out.fai.zip"
    bundle_path.write_bytes(b"previous bundle")
    with pytest.raises(InfrastructureError) as excinfo:
        cli_export.cmd_export(_args(bundle=str(bundle_path)))
    assert excinfo.value.exit_code == 3
    msg = str(excinfo.value).lower()
    assert "exists" in msg or "overwrite" in msg
    # And the previous file is untouched
    assert bundle_path.read_bytes() == b"previous bundle"


# ---------------------------------------------------------------------------
# (i) Existing output + --overwrite → exit 0
# ---------------------------------------------------------------------------


def test_existing_output_with_overwrite_returns_exit_0(tmp_path, monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([_clean_artifact()]))
    bundle_path = tmp_path / "out.fai.zip"
    bundle_path.write_bytes(b"previous bundle")
    rc = cli_export.cmd_export(_args(bundle=str(bundle_path), overwrite=True))
    assert rc == 0
    # The bundle was replaced with a real zip
    assert zipfile.is_zipfile(bundle_path)


# ---------------------------------------------------------------------------
# (j) :memory: store with no sessions → exit 3
# ---------------------------------------------------------------------------


def test_memory_store_with_no_sessions_returns_exit_3(tmp_path, monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([]))
    bundle_path = tmp_path / "out.fai.zip"
    with pytest.raises(InfrastructureError) as excinfo:
        cli_export.cmd_export(_args(bundle=str(bundle_path), store_path=":memory:"))
    assert excinfo.value.exit_code == 3


# ---------------------------------------------------------------------------
# (k) cmd_export reads args defensively
# ---------------------------------------------------------------------------


def test_cmd_export_reads_args_defensively(tmp_path, monkeypatch) -> None:
    """Construct argparse.Namespace WITHOUT the optional fields; should still work."""
    _patch_store(monkeypatch, _FakeStore([_clean_artifact()]))
    bundle_path = tmp_path / "out.fai.zip"
    args = argparse.Namespace(
        session_id="11111111-1111-1111-1111-111111111111",
        bundle=str(bundle_path),
        store_path=":memory:",
    )
    rc = cli_export.cmd_export(args)
    assert rc == 0


# ---------------------------------------------------------------------------
# (l) bundle_id determinism: same inputs + same exported_at → same id
# ---------------------------------------------------------------------------


def test_bundle_id_deterministic_across_two_cli_exports(tmp_path, monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([_clean_artifact()]))
    b1 = tmp_path / "b1.fai.zip"
    b2 = tmp_path / "b2.fai.zip"
    cli_export.cmd_export(_args(bundle=str(b1)))
    cli_export.cmd_export(_args(bundle=str(b2)))
    m1 = _read_manifest(b1)
    m2 = _read_manifest(b2)
    assert m1["bundle_id"] == m2["bundle_id"]


# ---------------------------------------------------------------------------
# (m) bundle_id sensitivity: different exported_at → different id
# ---------------------------------------------------------------------------


def test_bundle_id_differs_when_exported_at_differs(tmp_path, monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([_clean_artifact()]))
    b1 = tmp_path / "b1.fai.zip"
    b2 = tmp_path / "b2.fai.zip"
    cli_export.cmd_export(_args(bundle=str(b1), exported_at="2026-05-24T12:00:00+00:00"))
    cli_export.cmd_export(_args(bundle=str(b2), exported_at="2026-05-24T13:00:00+00:00"))
    m1 = _read_manifest(b1)
    m2 = _read_manifest(b2)
    assert m1["bundle_id"] != m2["bundle_id"]


# ---------------------------------------------------------------------------
# (n) Manifest contains every v3-schema field
# ---------------------------------------------------------------------------


def test_cli_export_manifest_has_all_v3_fields(tmp_path, monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([_clean_artifact()]))
    bundle_path = tmp_path / "out.fai.zip"
    cli_export.cmd_export(_args(bundle=str(bundle_path)))
    m = _read_manifest(bundle_path)
    for field in [
        "bundle_format_version",
        "manifest_schema_version",
        "bundle_type",
        "bundle_id",
        "text_encoding",
        "session_id",
        "exported_at",
        "export_tool",
        "export_tool_version",
        "falsifyai_version",
        "platform",
        "python_version",
        "exported_under_protest",
        "pre_export_integrity",
        "integrity_scope",
        "attestations",
        "signature_slots",
        "files",
    ]:
        assert field in m, f"manifest missing v3 field: {field}"


# ---------------------------------------------------------------------------
# Default exported_at when --exported-at omitted → current UTC time
# ---------------------------------------------------------------------------


def test_default_exported_at_uses_current_utc_time(tmp_path, monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([_clean_artifact()]))
    bundle_path = tmp_path / "out.fai.zip"
    before = datetime.now(UTC)
    cli_export.cmd_export(_args(bundle=str(bundle_path), exported_at=None))
    after = datetime.now(UTC)
    m = _read_manifest(bundle_path)
    exported_at = datetime.fromisoformat(m["exported_at"])
    assert before <= exported_at <= after


# ---------------------------------------------------------------------------
# Architectural assertion (co-located, mirrors PR-31 convention)
# ---------------------------------------------------------------------------


def test_export_does_not_import_resolver() -> None:
    """falsifyai.cli.export must not transitively import falsifyai.verdict.resolver.

    Mirrors test_diff_does_not_import_resolver and test_verify_does_not_import_resolver.
    Preservation discipline: export reads case.verdict from the loaded artifact,
    never re-resolves.
    """
    import sys

    for mod_name in list(sys.modules):
        if mod_name.startswith("falsifyai.cli.export"):
            del sys.modules[mod_name]
        if mod_name.startswith("falsifyai.bundle"):
            del sys.modules[mod_name]
        if mod_name == "falsifyai.verdict.resolver":
            del sys.modules[mod_name]

    import falsifyai.cli.export  # noqa: F401

    assert "falsifyai.verdict.resolver" not in sys.modules, (
        "falsifyai.cli.export must not import falsifyai.verdict.resolver "
        "(re-resolving violates the preservation guarantee). "
        "Read case.verdict from the loaded artifact instead."
    )
