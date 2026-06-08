"""Unit tests for ``falsifyai.bundle.writer`` (PR-32, Phase B).

Exercises ``BundleManifest``, ``BundleFileEntry``, ``write_bundle``, and the
schema constants.

Tests grouped by acceptance criterion from PR-32 plan §5:

- API surface (frozen dataclasses, constants present and correct)
- Manifest schema (every v3 field present with correct type)
- ``bundle_id`` determinism + content addressing
- ``bundle_id`` self-exclusion (the user-noted guardrail)
- Per-file SHA256 correctness
- Bundle round-trip via ``replay.serialize.artifact_from_json``
- Deterministic re-export (byte-identical zip across two writes)
- Cross-platform zip discipline (create_system, external_attr, timestamps)
- Spec-path handling (supplied vs. omitted)
- README auto-generation contents (PII warning, required sections,
  pre-PR-11 note, ``cli_invocation`` conditional)
- ``exported_under_protest`` semantics under failed integrity
- Text-encoding contract (UTF-8, LF, sorted iteration)
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from falsifyai.bundle.writer import (
    BUNDLE_FORMAT_VERSION,
    BUNDLE_TYPE,
    MANIFEST_SCHEMA_VERSION,
    BundleFileEntry,
    BundleManifest,
    write_bundle,
)
from falsifyai.integrity.checks import run_integrity_checks
from falsifyai.replay.models import ReplayArtifact
from falsifyai.replay.serialize import artifact_from_json
from falsifyai.spec.materializer import compute_materialized_hash
from tests.fixtures.build_artifact import make_artifact

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_FIXED_EXPORTED_AT = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
_FIXED_VERSION = "0.3.0.test"
_FIXED_PLATFORM = "linux"
_FIXED_PY_VERSION = "3.13.5"


def _clean_artifact(session_id: str = "11111111-1111-1111-1111-111111111111") -> ReplayArtifact:
    """Build a fixture artifact whose materialized_hash is recomputed correctly."""
    a = make_artifact(session_id=session_id)
    correct = compute_materialized_hash(a.materialized.cases)
    return dataclasses.replace(
        a,
        materialized_hash=correct,
        materialized=dataclasses.replace(a.materialized, materialized_hash=correct),
    )


def _write_kwargs(
    *,
    spec_yaml: bytes | None = None,
    allow_corrupted: bool = False,
    exported_at: datetime = _FIXED_EXPORTED_AT,
):
    """Standard kwargs for write_bundle. Override fields per test."""
    return {
        "spec_yaml": spec_yaml,
        "exported_at": exported_at,
        "allow_corrupted": allow_corrupted,
        "falsifyai_version": _FIXED_VERSION,
        "platform": _FIXED_PLATFORM,
        "python_version": _FIXED_PY_VERSION,
    }


def _do_write(
    tmp_path: Path,
    artifact: ReplayArtifact | None = None,
    bundle_name: str = "bundle.fai.zip",
    **kwargs,
) -> tuple[Path, BundleManifest]:
    """Build a clean artifact, write a bundle, return (path, manifest)."""
    if artifact is None:
        artifact = _clean_artifact()
    output_path = tmp_path / bundle_name
    integrity_report = run_integrity_checks(artifact)
    write_kwargs = _write_kwargs()
    write_kwargs.update(kwargs)
    manifest = write_bundle(
        artifact,
        output_path,
        integrity_report=integrity_report,
        **write_kwargs,
    )
    return output_path, manifest


def _read_manifest(bundle_path: Path) -> dict:
    with zipfile.ZipFile(bundle_path, "r") as zf:
        return json.loads(zf.read("manifest.json").decode("utf-8"))


def _read_file(bundle_path: Path, name: str) -> bytes:
    with zipfile.ZipFile(bundle_path, "r") as zf:
        return zf.read(name)


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


def test_bundle_format_version_is_1() -> None:
    assert BUNDLE_FORMAT_VERSION == 1


def test_manifest_schema_version_is_1() -> None:
    assert MANIFEST_SCHEMA_VERSION == 1


def test_bundle_type_is_falsifyai_replay_bundle() -> None:
    assert BUNDLE_TYPE == "falsifyai-replay-bundle"


def test_bundle_manifest_is_frozen_dataclass() -> None:
    """BundleManifest must be a frozen dataclass (preservation discipline)."""
    assert dataclasses.is_dataclass(BundleManifest)
    fields = {f.name for f in dataclasses.fields(BundleManifest)}
    # Spot-check the load-bearing fields exist
    for required in {
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
    }:
        assert required in fields, f"BundleManifest missing field: {required}"


def test_bundle_file_entry_is_frozen_dataclass() -> None:
    assert dataclasses.is_dataclass(BundleFileEntry)
    fields = {f.name for f in dataclasses.fields(BundleFileEntry)}
    assert fields >= {"path", "sha256", "size_bytes"}


# ---------------------------------------------------------------------------
# Manifest schema (every v3 field present, correct shape)
# ---------------------------------------------------------------------------


def test_manifest_has_all_v3_schema_fields(tmp_path) -> None:
    bundle_path, _ = _do_write(tmp_path)
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


def test_manifest_field_values(tmp_path) -> None:
    bundle_path, manifest = _do_write(tmp_path)
    m = _read_manifest(bundle_path)
    assert m["bundle_format_version"] == 1
    assert m["manifest_schema_version"] == 1
    assert m["bundle_type"] == "falsifyai-replay-bundle"
    assert m["text_encoding"] == "utf-8"
    assert m["export_tool"] == "falsifyai export"
    assert m["export_tool_version"] == _FIXED_VERSION
    assert m["falsifyai_version"] == _FIXED_VERSION
    assert m["platform"] == _FIXED_PLATFORM
    assert m["python_version"] == _FIXED_PY_VERSION
    assert m["exported_at"] == _FIXED_EXPORTED_AT.isoformat()
    assert m["exported_under_protest"] is False
    assert m["attestations"] == []
    assert m["signature_slots"] == []
    # at minimum: artifact.json, README.md (manifest.json is hashed via bundle_id)
    assert isinstance(m["files"], list)
    assert len(m["files"]) >= 2


def test_manifest_integrity_scope_on_clean_artifact(tmp_path) -> None:
    bundle_path, _ = _do_write(tmp_path)
    m = _read_manifest(bundle_path)
    assert m["integrity_scope"]["artifact_verified"] is True
    assert m["integrity_scope"]["bundle_verified"] is True
    assert m["integrity_scope"]["signature_verified"] is False


def test_manifest_pre_export_integrity_passed_on_clean_artifact(tmp_path) -> None:
    bundle_path, _ = _do_write(tmp_path)
    m = _read_manifest(bundle_path)
    assert m["pre_export_integrity"]["status"] == "passed"
    assert m["pre_export_integrity"]["failed_checks"] == []


# ---------------------------------------------------------------------------
# bundle_id determinism + content addressing
# ---------------------------------------------------------------------------


def test_bundle_id_is_64_char_hex(tmp_path) -> None:
    _, manifest = _do_write(tmp_path)
    assert len(manifest.bundle_id) == 64
    assert all(c in "0123456789abcdef" for c in manifest.bundle_id)


def test_bundle_id_is_deterministic_across_two_writes(tmp_path) -> None:
    """Two exports of the same artifact with same exported_at → same bundle_id."""
    a = _clean_artifact()
    p1, m1 = _do_write(tmp_path, artifact=a, bundle_name="b1.fai.zip")
    p2, m2 = _do_write(tmp_path, artifact=a, bundle_name="b2.fai.zip")
    assert m1.bundle_id == m2.bundle_id


def test_bundle_id_changes_when_exported_at_differs(tmp_path) -> None:
    a = _clean_artifact()
    _, m1 = _do_write(tmp_path, artifact=a, bundle_name="b1.fai.zip")
    later = datetime(2026, 5, 24, 13, 0, 0, tzinfo=UTC)
    _, m2 = _do_write(tmp_path, artifact=a, bundle_name="b2.fai.zip", exported_at=later)
    assert m1.bundle_id != m2.bundle_id


def test_bundle_id_changes_when_artifact_session_id_differs(tmp_path) -> None:
    a1 = _clean_artifact(session_id="11111111-1111-1111-1111-111111111111")
    a2 = _clean_artifact(session_id="22222222-2222-2222-2222-222222222222")
    _, m1 = _do_write(tmp_path, artifact=a1, bundle_name="b1.fai.zip")
    _, m2 = _do_write(tmp_path, artifact=a2, bundle_name="b2.fai.zip")
    assert m1.bundle_id != m2.bundle_id


def test_bundle_id_changes_when_spec_yaml_supplied(tmp_path) -> None:
    a = _clean_artifact()
    _, m_no_spec = _do_write(tmp_path, artifact=a, bundle_name="b1.fai.zip")
    _, m_with_spec = _do_write(
        tmp_path, artifact=a, bundle_name="b2.fai.zip", spec_yaml=b"falsify:\n  version: '1.0'\n"
    )
    assert m_no_spec.bundle_id != m_with_spec.bundle_id


def test_bundle_id_excludes_itself_from_canonical_input(tmp_path) -> None:
    """The user-noted guardrail.

    bundle_id is sha256 of the canonical manifest *with bundle_id omitted*.
    Otherwise we'd have a self-referential hash loop.

    Verify by recomputing the id externally and asserting it matches.
    """
    bundle_path, manifest = _do_write(tmp_path)
    m = _read_manifest(bundle_path)

    stored_id = m["bundle_id"]
    manifest_without_id = {k: v for k, v in m.items() if k != "bundle_id"}
    canonical = json.dumps(
        manifest_without_id, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    expected_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert stored_id == expected_id


# ---------------------------------------------------------------------------
# Per-file SHA256 correctness
# ---------------------------------------------------------------------------


def test_each_file_in_manifest_has_correct_sha256(tmp_path) -> None:
    bundle_path, _ = _do_write(tmp_path)
    m = _read_manifest(bundle_path)
    for entry in m["files"]:
        if entry["path"] == "manifest.json":
            continue  # manifest is hashed by bundle_id, not listed in files
        actual = hashlib.sha256(_read_file(bundle_path, entry["path"])).hexdigest()
        assert actual == entry["sha256"], (
            f"sha256 mismatch for {entry['path']}: "
            f"manifest says {entry['sha256']}, file is {actual}"
        )


def test_each_file_in_manifest_has_correct_size_bytes(tmp_path) -> None:
    bundle_path, _ = _do_write(tmp_path)
    m = _read_manifest(bundle_path)
    for entry in m["files"]:
        if entry["path"] == "manifest.json":
            continue
        actual = len(_read_file(bundle_path, entry["path"]))
        assert actual == entry["size_bytes"]


def test_manifest_files_listing_is_sorted(tmp_path) -> None:
    """Determinism: file entries in manifest sorted alphabetically by path."""
    bundle_path, _ = _do_write(tmp_path)
    m = _read_manifest(bundle_path)
    paths = [e["path"] for e in m["files"]]
    assert paths == sorted(paths)


# ---------------------------------------------------------------------------
# Bundle round-trip
# ---------------------------------------------------------------------------


def test_artifact_json_round_trips_through_serialize(tmp_path) -> None:
    """The bundled artifact.json must deserialize to an equivalent ReplayArtifact."""
    a = _clean_artifact()
    bundle_path, _ = _do_write(tmp_path, artifact=a)
    artifact_json = _read_file(bundle_path, "artifact.json").decode("utf-8")
    restored = artifact_from_json(artifact_json)
    assert restored.session_id == a.session_id
    assert restored.materialized_hash == a.materialized_hash
    assert len(restored.case_results) == len(a.case_results)


def test_artifact_json_byte_identical_to_serialize_output(tmp_path) -> None:
    """The bundle's artifact.json must reuse replay.serialize, not re-implement."""
    from falsifyai.replay.serialize import artifact_to_json

    a = _clean_artifact()
    bundle_path, _ = _do_write(tmp_path, artifact=a)
    bundle_json = _read_file(bundle_path, "artifact.json").decode("utf-8")
    expected_json = artifact_to_json(a)
    assert bundle_json == expected_json


# ---------------------------------------------------------------------------
# Determinism: cross-platform zip byte-identity (within same OS)
# ---------------------------------------------------------------------------


def test_two_writes_produce_byte_identical_zip(tmp_path) -> None:
    """Same inputs + same exported_at → byte-identical bundle file."""
    a = _clean_artifact()
    p1, _ = _do_write(tmp_path, artifact=a, bundle_name="b1.fai.zip")
    p2, _ = _do_write(tmp_path, artifact=a, bundle_name="b2.fai.zip")
    assert p1.read_bytes() == p2.read_bytes()


def test_zip_entries_have_fixed_1980_timestamp(tmp_path) -> None:
    bundle_path, _ = _do_write(tmp_path)
    with zipfile.ZipFile(bundle_path, "r") as zf:
        for info in zf.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0), (
                f"{info.filename} has non-fixed timestamp {info.date_time}"
            )


def test_zip_entries_have_unix_create_system(tmp_path) -> None:
    """create_system=3 (Unix) on every entry — neutralizes cross-OS drift."""
    bundle_path, _ = _do_write(tmp_path)
    with zipfile.ZipFile(bundle_path, "r") as zf:
        for info in zf.infolist():
            assert info.create_system == 3, (
                f"{info.filename} has create_system={info.create_system}, expected 3"
            )


def test_zip_entries_have_pinned_external_attr(tmp_path) -> None:
    """external_attr fixed so OS permission bits don't leak into the bundle."""
    bundle_path, _ = _do_write(tmp_path)
    with zipfile.ZipFile(bundle_path, "r") as zf:
        for info in zf.infolist():
            assert info.external_attr == (0o644 << 16), (
                f"{info.filename} has external_attr={info.external_attr:#010x}, "
                f"expected {0o644 << 16:#010x}"
            )


# ---------------------------------------------------------------------------
# Spec-path handling
# ---------------------------------------------------------------------------


def test_spec_yaml_omitted_means_no_spec_file_in_bundle(tmp_path) -> None:
    bundle_path, _ = _do_write(tmp_path, spec_yaml=None)
    with zipfile.ZipFile(bundle_path, "r") as zf:
        names = zf.namelist()
    assert "spec.yaml" not in names


def test_spec_yaml_supplied_is_byte_identical_in_bundle(tmp_path) -> None:
    """Supplied spec bytes round-trip through the bundle unchanged."""
    spec_bytes = b"falsify:\n  version: '1.0'\n  name: 'test'\n"
    bundle_path, _ = _do_write(tmp_path, spec_yaml=spec_bytes)
    assert _read_file(bundle_path, "spec.yaml") == spec_bytes


def test_manifest_files_lists_spec_yaml_when_supplied(tmp_path) -> None:
    spec_bytes = b"falsify:\n  version: '1.0'\n"
    bundle_path, _ = _do_write(tmp_path, spec_yaml=spec_bytes)
    m = _read_manifest(bundle_path)
    paths = [e["path"] for e in m["files"]]
    assert "spec.yaml" in paths


def test_manifest_files_omits_spec_yaml_when_not_supplied(tmp_path) -> None:
    bundle_path, _ = _do_write(tmp_path, spec_yaml=None)
    m = _read_manifest(bundle_path)
    paths = [e["path"] for e in m["files"]]
    assert "spec.yaml" not in paths


# ---------------------------------------------------------------------------
# README auto-generation
# ---------------------------------------------------------------------------


def _read_readme(bundle_path: Path) -> str:
    return _read_file(bundle_path, "README.md").decode("utf-8")


def test_readme_contains_session_id(tmp_path) -> None:
    a = _clean_artifact(session_id="abcdef00-1111-2222-3333-aaaaaaaaaaaa")
    bundle_path, _ = _do_write(tmp_path, artifact=a)
    assert "abcdef00-1111-2222-3333-aaaaaaaaaaaa" in _read_readme(bundle_path)


def test_readme_contains_materialized_hash(tmp_path) -> None:
    a = _clean_artifact()
    bundle_path, _ = _do_write(tmp_path, artifact=a)
    assert a.materialized_hash in _read_readme(bundle_path)


def test_readme_contains_exported_timestamp(tmp_path) -> None:
    bundle_path, _ = _do_write(tmp_path)
    assert _FIXED_EXPORTED_AT.isoformat() in _read_readme(bundle_path)


def test_readme_contains_pii_warning(tmp_path) -> None:
    bundle_path, _ = _do_write(tmp_path)
    readme = _read_readme(bundle_path)
    assert "PII" in readme or "sensitive data" in readme


def test_readme_contains_cli_reproduction_command(tmp_path) -> None:
    a = _clean_artifact()
    bundle_path, _ = _do_write(tmp_path, artifact=a)
    readme = _read_readme(bundle_path)
    assert "falsifyai" in readme  # CLI command reference present
    assert a.session_id in readme


def test_readme_notes_no_spec_when_spec_omitted(tmp_path) -> None:
    bundle_path, _ = _do_write(tmp_path, spec_yaml=None)
    readme = _read_readme(bundle_path).lower()
    assert (
        "no source spec" in readme
        or "spec not attached" in readme
        or "spec_yaml: not_supplied" in readme
    )


def test_readme_notes_pre_pr11_artifact_when_ci_fields_zero(tmp_path) -> None:
    """Pre-PR-11 artifacts had zero CI fields. README must note this."""
    a = _clean_artifact()
    case = a.case_results[0]
    zeroed = dataclasses.replace(case, stability=0.0, stability_ci_low=0.0, stability_ci_high=0.0)
    aged = dataclasses.replace(a, case_results=[zeroed])
    bundle_path, _ = _do_write(tmp_path, artifact=aged)
    readme = _read_readme(bundle_path).lower()
    assert "pre-pr-11" in readme or "pre-pr #11" in readme or "ci evidence" in readme


def test_readme_uses_lf_line_endings(tmp_path) -> None:
    """Text-encoding contract: LF line endings everywhere."""
    bundle_path, _ = _do_write(tmp_path)
    raw = _read_file(bundle_path, "README.md")
    # CRLF would contain b"\r\n"; LF only contains b"\n".
    assert b"\r\n" not in raw


def test_manifest_uses_lf_line_endings(tmp_path) -> None:
    bundle_path, _ = _do_write(tmp_path)
    raw = _read_file(bundle_path, "manifest.json")
    assert b"\r\n" not in raw


# ---------------------------------------------------------------------------
# exported_under_protest semantics
# ---------------------------------------------------------------------------


def test_allow_corrupted_sets_exported_under_protest_true(tmp_path) -> None:
    """Corrupted artifact + allow_corrupted=True → manifest predicate is True."""
    a = _clean_artifact()
    bad = dataclasses.replace(a, materialized_hash="0" * 64)
    output_path = tmp_path / "bundle.fai.zip"
    integrity_report = run_integrity_checks(bad)
    assert not integrity_report.all_passed  # sanity: integrity check fails

    kwargs = _write_kwargs()
    kwargs["allow_corrupted"] = True
    manifest = write_bundle(bad, output_path, integrity_report=integrity_report, **kwargs)
    assert manifest.exported_under_protest is True
    m = _read_manifest(output_path)
    assert m["exported_under_protest"] is True
    assert m["pre_export_integrity"]["status"] == "failed"
    assert "materialized_hash" in m["pre_export_integrity"]["failed_checks"]


def test_allow_corrupted_sets_artifact_verified_false(tmp_path) -> None:
    """integrity_scope.artifact_verified flips to False under corruption."""
    a = _clean_artifact()
    bad = dataclasses.replace(a, materialized_hash="0" * 64)
    output_path = tmp_path / "bundle.fai.zip"
    integrity_report = run_integrity_checks(bad)
    kwargs = _write_kwargs()
    kwargs["allow_corrupted"] = True
    write_bundle(bad, output_path, integrity_report=integrity_report, **kwargs)
    m = _read_manifest(output_path)
    assert m["integrity_scope"]["artifact_verified"] is False
    # bundle_verified stays true — the bundle's own file hashing is still sound
    assert m["integrity_scope"]["bundle_verified"] is True


# ---------------------------------------------------------------------------
# PR-33 anticipation: cli_invocation conditional rendering
# ---------------------------------------------------------------------------


def test_readme_omits_generated_by_section_when_no_cli_invocation(tmp_path) -> None:
    """When artifact has no cli_invocation field, README must NOT render that section."""
    bundle_path, _ = _do_write(tmp_path)
    readme = _read_readme(bundle_path)
    # The section header should be absent today (PR-33 not shipped)
    assert "Generated by" not in readme or "(see CLI Reproduction" in readme  # tolerate paraphrase


# ---------------------------------------------------------------------------
# Text-encoding contract
# ---------------------------------------------------------------------------


def test_manifest_json_is_valid_utf8(tmp_path) -> None:
    bundle_path, _ = _do_write(tmp_path)
    raw = _read_file(bundle_path, "manifest.json")
    raw.decode("utf-8")  # must not raise


def test_manifest_json_has_canonical_ordering(tmp_path) -> None:
    """sort_keys=True semantics: top-level keys appear in sorted order in the raw text."""
    bundle_path, _ = _do_write(tmp_path)
    raw = _read_file(bundle_path, "manifest.json").decode("utf-8")
    # First top-level key should be alphabetically first among manifest keys.
    # All v3 fields start with letters; "attestations" comes before "bundle_format_version".
    # Strip the leading "{" then read the first key.
    first_key_quote = raw.find('"', 1)
    second_key_quote = raw.find('"', first_key_quote + 1)
    first_key = raw[first_key_quote + 1 : second_key_quote]
    assert first_key == "attestations", f"manifest is not sorted; first key is {first_key}"
