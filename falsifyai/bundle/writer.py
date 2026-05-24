"""Bundle writer: produces deterministic portable evidence packages (PR-32).

Discipline:

- **No re-resolution.** Reads ``artifact.case_results[*].verdict`` from the
  loaded artifact; never invokes ``falsifyai.verdict.resolver``. Enforced by
  the architectural test in ``tests/unit/test_cli_export.py``.
- **No IO at function boundary except the final zip write.** Inputs are
  data; output is one file plus a returned manifest object.
- **Deterministic by construction.** Same artifact + same ``exported_at`` →
  byte-identical zip. Hand-constructed ``ZipInfo`` with ``create_system=3``,
  ``external_attr=(0o644 << 16)``, fixed 1980 timestamp. Sorted entry order.
  Canonical JSON via ``replay.serialize.artifact_to_json``.

The bundle is **preservation infrastructure, not interpretation
infrastructure.** No analytics, no scoring, no redaction, no taxonomy.

**Content addressing (bundle_id):** sha256 of the canonical-JSON
serialization of the manifest with the ``bundle_id`` field omitted. The id
transitively covers every file hash in ``files[]`` plus all metadata
fields. The README does NOT embed ``bundle_id`` (that would create a
self-referential hash loop); ``manifest.json`` is the authoritative
location for the id.
"""

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from falsifyai.integrity.checks import CheckStatus, IntegrityReport
from falsifyai.replay.models import ReplayArtifact
from falsifyai.replay.serialize import artifact_to_json

BUNDLE_FORMAT_VERSION: int = 1
MANIFEST_SCHEMA_VERSION: int = 1
BUNDLE_TYPE: str = "falsifyai-replay-bundle"

_FIXED_ZIP_TIMESTAMP: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0)
_UNIX_CREATE_SYSTEM: int = 3  # neutralizes cross-platform drift in ZipInfo
_FIXED_EXTERNAL_ATTR: int = 0o644 << 16  # pinned permission bits


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BundleFileEntry:
    """One file in the bundle's manifest: path, SHA256, size in bytes."""

    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class BundleManifest:
    """The manifest payload written as ``manifest.json`` and returned to caller."""

    bundle_format_version: int
    manifest_schema_version: int
    bundle_type: str
    bundle_id: str
    text_encoding: str
    session_id: str
    exported_at: str
    export_tool: str
    export_tool_version: str
    falsifyai_version: str
    platform: str
    python_version: str
    exported_under_protest: bool
    pre_export_integrity: dict[str, Any]
    integrity_scope: dict[str, bool]
    attestations: list[Any] = field(default_factory=list)
    signature_slots: list[Any] = field(default_factory=list)
    files: list[BundleFileEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _canonical_json(payload: Any) -> bytes:
    """Canonical JSON: UTF-8 bytes, sorted keys, compact separators."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest_to_dict(manifest: BundleManifest) -> dict[str, Any]:
    """Convert BundleManifest → dict for JSON serialization."""
    return {
        "bundle_format_version": manifest.bundle_format_version,
        "manifest_schema_version": manifest.manifest_schema_version,
        "bundle_type": manifest.bundle_type,
        "bundle_id": manifest.bundle_id,
        "text_encoding": manifest.text_encoding,
        "session_id": manifest.session_id,
        "exported_at": manifest.exported_at,
        "export_tool": manifest.export_tool,
        "export_tool_version": manifest.export_tool_version,
        "falsifyai_version": manifest.falsifyai_version,
        "platform": manifest.platform,
        "python_version": manifest.python_version,
        "exported_under_protest": manifest.exported_under_protest,
        "pre_export_integrity": manifest.pre_export_integrity,
        "integrity_scope": manifest.integrity_scope,
        "attestations": list(manifest.attestations),
        "signature_slots": list(manifest.signature_slots),
        "files": [
            {"path": e.path, "sha256": e.sha256, "size_bytes": e.size_bytes} for e in manifest.files
        ],
    }


def _compute_bundle_id(manifest_dict_with_placeholder: dict[str, Any]) -> str:
    """Derive bundle_id from the manifest dict with the bundle_id field omitted."""
    without_id = {k: v for k, v in manifest_dict_with_placeholder.items() if k != "bundle_id"}
    return _hash_bytes(_canonical_json(without_id))


def _build_integrity_blocks(
    report: IntegrityReport, *, allow_corrupted: bool
) -> tuple[dict[str, Any], dict[str, bool], bool]:
    """Compute (pre_export_integrity, integrity_scope, exported_under_protest)."""
    failed_checks = [r.name for r in report.results if r.status is CheckStatus.FAIL]
    status = "passed" if report.all_passed else "failed"
    pre_export_integrity = {"status": status, "failed_checks": failed_checks}

    integrity_scope = {
        "artifact_verified": report.all_passed,
        "bundle_verified": True,  # bundle's own file hashing is sound regardless
        "signature_verified": False,  # no signing yet
    }
    exported_under_protest = (not report.all_passed) and allow_corrupted
    return pre_export_integrity, integrity_scope, exported_under_protest


def _is_pre_pr11_artifact(artifact: ReplayArtifact) -> bool:
    """Heuristic: zero CI fields across all cases → pre-PR-11 artifact."""
    return all(
        c.stability == 0.0 and c.stability_ci_low == 0.0 and c.stability_ci_high == 0.0
        for c in artifact.case_results
    )


def _generate_readme(
    artifact: ReplayArtifact,
    *,
    exported_at: str,
    falsifyai_version: str,
    platform: str,
    python_version: str,
    exported_under_protest: bool,
    pre_export_integrity_status: str,
    spec_yaml_attached: bool,
) -> str:
    """Build the bundle's README.md as deterministic Markdown.

    Does NOT embed bundle_id (would create a self-referential hash loop —
    bundle_id depends on README hash via files[], so README must be
    independent of bundle_id). The authoritative bundle_id lives in
    manifest.json.
    """
    lines: list[str] = []

    lines.append("# FalsifyAI Replay Bundle")
    lines.append("")
    lines.append("This bundle preserves one `ReplayArtifact` and its full evidence trail.")
    lines.append("")

    lines.append("## Bundle metadata")
    lines.append("")
    lines.append(f"- exported_at: `{exported_at}`")
    lines.append(f"- falsifyai_version: `{falsifyai_version}`")
    lines.append(f"- platform: `{platform}`")
    lines.append(f"- python_version: `{python_version}`")
    lines.append("")
    lines.append("The authoritative `bundle_id` content address lives in `manifest.json`.")
    lines.append("")

    lines.append("## Artifact identity")
    lines.append("")
    lines.append(f"- session_id: `{artifact.session_id}`")
    lines.append(f"- spec_hash: `{artifact.spec_hash}`")
    lines.append(f"- materialized_hash: `{artifact.materialized_hash}`")
    lines.append(f"- created_at: `{artifact.created_at.isoformat()}`")
    lines.append(f"- artifact_version: `{artifact.falsifyai_version}`")
    lines.append("")

    lines.append("## Integrity status")
    lines.append("")
    lines.append(f"- pre_export_integrity: **{pre_export_integrity_status}**")
    if exported_under_protest:
        lines.append("- exported_under_protest: **true**")
        lines.append("")
        lines.append(
            "WARNING: this bundle was produced from an artifact that failed "
            "integrity checks. It is NOT WORM-suitable evidence. See "
            "`manifest.json` `pre_export_integrity.failed_checks` for details."
        )
    lines.append("")

    lines.append("## Source spec")
    lines.append("")
    if spec_yaml_attached:
        lines.append("`spec.yaml` is attached in this bundle (byte-identical to the source).")
    else:
        lines.append(
            "No source spec attached (`spec_yaml: not_supplied`). The "
            "`materialized_hash` anchors the realized perturbations, but the "
            "original YAML was not provided at export time. Re-supply via "
            "`falsifyai export --spec-path <file>` to attach."
        )
    lines.append("")

    if _is_pre_pr11_artifact(artifact):
        lines.append("## Pre-PR-11 note")
        lines.append("")
        lines.append(
            "This artifact predates PR #11 resolver CI evidence; per-case "
            "stability bounds were not computed at run time. The verdict is "
            "still authoritative for what the resolver said at the time of run."
        )
        lines.append("")

    cli_invocation = getattr(artifact, "cli_invocation", None)
    if cli_invocation:
        lines.append("## Generated by")
        lines.append("")
        lines.append("```")
        lines.append(str(cli_invocation))
        lines.append("```")
        lines.append("")

    lines.append("## Privacy notice")
    lines.append("")
    lines.append(
        "This bundle preserves all input text verbatim. Review for PII or "
        "sensitive data before distribution."
    )
    lines.append("")

    lines.append("## CLI Reproduction")
    lines.append("")
    lines.append("Verify this bundle's artifact integrity:")
    lines.append("")
    lines.append("```bash")
    lines.append(f"falsifyai verify {artifact.session_id} --store-path <your-store>")
    lines.append("```")
    lines.append("")
    lines.append("Inspect the preserved evidence per case:")
    lines.append("")
    lines.append("```bash")
    lines.append(f"falsifyai inspect {artifact.session_id} --full --store-path <your-store>")
    lines.append("```")

    # LF line endings, single trailing newline.
    return "\n".join(lines) + "\n"


def _write_zip_entry(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
    """Write one entry with pinned ZipInfo fields (cross-platform deterministic)."""
    info = zipfile.ZipInfo(filename=name, date_time=_FIXED_ZIP_TIMESTAMP)
    info.create_system = _UNIX_CREATE_SYSTEM
    info.external_attr = _FIXED_EXTERNAL_ATTR
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, data)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_bundle(
    artifact: ReplayArtifact,
    output_path: str | Path,
    *,
    spec_yaml: bytes | None,
    exported_at: datetime,
    integrity_report: IntegrityReport,
    allow_corrupted: bool = False,
    falsifyai_version: str,
    platform: str,
    python_version: str,
) -> BundleManifest:
    """Write a deterministic portable evidence bundle to ``output_path``.

    Args:
        artifact: the loaded ``ReplayArtifact`` to export.
        output_path: where to write the bundle (``.fai.zip`` recommended).
        spec_yaml: source spec YAML bytes; ``None`` if not supplied.
        exported_at: UTC timestamp pinned in manifest.
        integrity_report: result of ``run_integrity_checks(artifact)``.
        allow_corrupted: when True, write the bundle even if integrity
            checks failed; manifest records the failure via
            ``exported_under_protest=true``.
        falsifyai_version: runtime version string for provenance.
        platform: ``sys.platform`` value for provenance.
        python_version: Python interpreter version for provenance.

    Returns:
        :class:`BundleManifest` (with ``bundle_id`` populated).

    Raises:
        ValueError: if ``allow_corrupted`` is False and integrity failed.
            (Caller normally checks ``integrity_report.all_passed`` first
            and raises its own ``InfrastructureError``; this is a guard.)
    """
    if not integrity_report.all_passed and not allow_corrupted:
        raise ValueError("refusing to bundle: integrity checks failed and allow_corrupted=False")

    output_path = Path(output_path)

    # 1. Serialize the artifact.
    artifact_json_bytes = artifact_to_json(artifact).encode("utf-8")

    # 2. Compute integrity blocks (needed by README for its status section).
    pre_export_integrity, integrity_scope, exported_under_protest = _build_integrity_blocks(
        integrity_report, allow_corrupted=allow_corrupted
    )

    # 3. Generate README — independent of bundle_id (no self-reference).
    readme_bytes = _generate_readme(
        artifact,
        exported_at=exported_at.isoformat(),
        falsifyai_version=falsifyai_version,
        platform=platform,
        python_version=python_version,
        exported_under_protest=exported_under_protest,
        pre_export_integrity_status=pre_export_integrity["status"],
        spec_yaml_attached=spec_yaml is not None,
    ).encode("utf-8")

    # 4. Build the file-entries list, sorted by path.
    files_payload: dict[str, bytes] = {
        "artifact.json": artifact_json_bytes,
        "README.md": readme_bytes,
    }
    if spec_yaml is not None:
        files_payload["spec.yaml"] = spec_yaml

    file_entries = sorted(
        (
            BundleFileEntry(path=name, sha256=_hash_bytes(data), size_bytes=len(data))
            for name, data in files_payload.items()
        ),
        key=lambda e: e.path,
    )

    # 5. Build the manifest with a placeholder bundle_id, then derive the real id.
    manifest_placeholder = BundleManifest(
        bundle_format_version=BUNDLE_FORMAT_VERSION,
        manifest_schema_version=MANIFEST_SCHEMA_VERSION,
        bundle_type=BUNDLE_TYPE,
        bundle_id="",
        text_encoding="utf-8",
        session_id=artifact.session_id,
        exported_at=exported_at.isoformat(),
        export_tool="falsifyai export",
        export_tool_version=falsifyai_version,
        falsifyai_version=falsifyai_version,
        platform=platform,
        python_version=python_version,
        exported_under_protest=exported_under_protest,
        pre_export_integrity=pre_export_integrity,
        integrity_scope=integrity_scope,
        attestations=[],
        signature_slots=[],
        files=file_entries,
    )
    bundle_id = _compute_bundle_id(_manifest_to_dict(manifest_placeholder))

    # 6. Final manifest with the derived id.
    final_manifest = BundleManifest(
        bundle_format_version=BUNDLE_FORMAT_VERSION,
        manifest_schema_version=MANIFEST_SCHEMA_VERSION,
        bundle_type=BUNDLE_TYPE,
        bundle_id=bundle_id,
        text_encoding="utf-8",
        session_id=artifact.session_id,
        exported_at=exported_at.isoformat(),
        export_tool="falsifyai export",
        export_tool_version=falsifyai_version,
        falsifyai_version=falsifyai_version,
        platform=platform,
        python_version=python_version,
        exported_under_protest=exported_under_protest,
        pre_export_integrity=pre_export_integrity,
        integrity_scope=integrity_scope,
        attestations=[],
        signature_slots=[],
        files=file_entries,
    )
    manifest_json_bytes = _canonical_json(_manifest_to_dict(final_manifest))

    # 7. Write the zip with sorted entry order + pinned ZipInfo.
    all_entries: dict[str, bytes] = {
        "manifest.json": manifest_json_bytes,
        "artifact.json": artifact_json_bytes,
        "README.md": readme_bytes,
    }
    if spec_yaml is not None:
        all_entries["spec.yaml"] = spec_yaml

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(all_entries.keys()):
            _write_zip_entry(zf, name, all_entries[name])

    return final_manifest
