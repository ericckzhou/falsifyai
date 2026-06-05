"""``falsifyai export <session_id> --bundle <output>`` — portable evidence bundles (PR-32).

Loads one stored ``ReplayArtifact``, runs integrity checks
(:mod:`falsifyai.integrity.checks`), and writes a deterministic
``.fai.zip`` bundle via :mod:`falsifyai.bundle.writer`.

Invariants:

- ``cmd_export`` is strictly read-only on the store. It never modifies a
  stored artifact.
- The bundle's per-case verdicts are read from the artifact; never
  re-resolved. Asserted by
  ``tests/unit/test_cli_export.py::test_export_does_not_import_resolver``.
- Exit codes:
    - 0 SUCCESS — bundle written, all integrity checks passed
      (or ``--allow-corrupted`` honored)
    - 3 ERROR — session not found, store unreadable, output path
      unwritable, or parent directory missing
    - 7 INTEGRITY_FAILURE — pre-export integrity check failed and
      ``--allow-corrupted`` was not supplied
"""

import argparse
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

from falsifyai.bundle.writer import BundleManifest, write_bundle
from falsifyai.cli import render
from falsifyai.cli.errors import InfrastructureError
from falsifyai.integrity.checks import run_integrity_checks
from falsifyai.replay.protocol import SessionNotFoundError
from falsifyai.replay.registry import build_store

INTEGRITY_FAILURE_EXIT_CODE: int = 7


def _falsifyai_version() -> str:
    """Best-effort runtime version string. Falls back to a sentinel for dev installs."""
    try:
        return _pkg_version("falsifyai")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def _resolve_exported_at(raw: str | None) -> datetime:
    """Parse --exported-at or default to current UTC time."""
    if raw is None:
        return datetime.now(UTC)
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise InfrastructureError(
            f"invalid --exported-at value (expected ISO 8601): {raw}"
        ) from exc
    if dt.tzinfo is None:
        raise InfrastructureError(f"--exported-at must be timezone-aware: {raw}")
    return dt


def cmd_export(args: argparse.Namespace) -> int:
    """Entry point for the ``export`` subcommand. Returns an exit code."""
    session_id: str | None = getattr(args, "session_id", None)
    bundle_raw: str | None = getattr(args, "bundle", None)
    spec_path_raw: str | None = getattr(args, "spec_path", None)
    allow_corrupted: bool = getattr(args, "allow_corrupted", False)
    overwrite: bool = getattr(args, "overwrite", False)
    exported_at_raw: str | None = getattr(args, "exported_at", None)
    store_path: str = getattr(args, "store_path", ".falsifyai/replays.db")

    if not session_id:
        raise InfrastructureError("session_id is required")
    if not bundle_raw:
        raise InfrastructureError("--bundle <output_path> is required")

    output_path = Path(bundle_raw)
    parent = output_path.parent
    if str(parent) not in ("", ".") and not parent.exists():
        raise InfrastructureError(
            f"parent directory does not exist: {parent} (create it or choose a different path)"
        )
    if output_path.exists() and not overwrite:
        raise InfrastructureError(f"output path exists; pass --overwrite to replace: {output_path}")

    spec_yaml: bytes | None = None
    if spec_path_raw is not None:
        spec_path = Path(spec_path_raw)
        if not spec_path.exists():
            raise InfrastructureError(f"--spec-path file does not exist: {spec_path}")
        spec_yaml = spec_path.read_bytes()

    exported_at = _resolve_exported_at(exported_at_raw)

    store = build_store(store_path)
    try:
        try:
            artifact = store.load_session(session_id)
        except SessionNotFoundError as exc:
            raise InfrastructureError(f"session not found: {session_id}") from exc

        integrity_report = run_integrity_checks(artifact)
        if not integrity_report.all_passed and not allow_corrupted:
            # Refuse-by-default: do not write the bundle.
            render.render_export_refusal(
                integrity_report,
                session_id=session_id,
                output_path=output_path,
            )
            return INTEGRITY_FAILURE_EXIT_CODE

        manifest = write_bundle(
            artifact,
            output_path,
            spec_yaml=spec_yaml,
            exported_at=exported_at,
            integrity_report=integrity_report,
            allow_corrupted=allow_corrupted,
            falsifyai_version=_falsifyai_version(),
            platform=sys.platform,
            python_version=sys.version.split()[0],
        )
        _render_warning_if_under_protest(manifest)
        render.render_export(manifest, output_path=output_path)
        return 0
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()


def _render_warning_if_under_protest(manifest: BundleManifest) -> None:
    """Emit a stderr warning when --allow-corrupted produced a non-WORM bundle."""
    if manifest.exported_under_protest:
        print(
            "WARNING: bundle is NOT WORM-suitable; produced from corrupted artifact. "
            f"failed_checks={manifest.pre_export_integrity['failed_checks']}",
            file=sys.stderr,
        )


__all__ = ["INTEGRITY_FAILURE_EXIT_CODE", "cmd_export"]
