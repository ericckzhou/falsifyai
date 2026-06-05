"""``falsifyai verify <session_id>`` — replay-artifact integrity validation (PR-31).

Loads one (or, with ``--all``, every) stored ``ReplayArtifact`` from the
configured ``ReplayStore``, runs 8 integrity checks via
:mod:`falsifyai.integrity.checks`, and renders the result.

Invariants:

- ``cmd_verify`` is strictly read-only. It never modifies a stored artifact.
- The verdict on each case is read from the artifact, never re-resolved.
  Asserted by ``tests/unit/test_cli_verify.py::test_verify_does_not_import_resolver``.
- Exit codes:
    - 0 SUCCESS — every check on every loaded artifact passed
    - 3 ERROR — session not found, store unreadable, or argparse-shouldn't-allow misuse
    - 7 INTEGRITY_FAILURE — at least one check on at least one artifact failed
"""

import argparse

from falsifyai.cli import render
from falsifyai.cli.errors import InfrastructureError
from falsifyai.integrity.checks import IntegrityReport, run_integrity_checks
from falsifyai.replay.protocol import ReplayStore, SessionNotFoundError
from falsifyai.replay.registry import build_store

INTEGRITY_FAILURE_EXIT_CODE: int = 7


def _verify_single(store: ReplayStore, session_id: str) -> IntegrityReport:
    try:
        artifact = store.load_session(session_id)
    except SessionNotFoundError as exc:
        raise InfrastructureError(f"session not found: {session_id}") from exc
    return run_integrity_checks(artifact)


def _verify_all(store: ReplayStore) -> list[IntegrityReport]:
    return [run_integrity_checks(a) for a in store.query_sessions(limit=10_000)]


def cmd_verify(args: argparse.Namespace) -> int:
    """Entry point for the ``verify`` subcommand. Returns an exit code."""
    all_sessions: bool = getattr(args, "all", False)
    session_id: str | None = getattr(args, "session_id", None)

    if not all_sessions and not session_id:
        raise InfrastructureError("session_id is required (or pass --all)")

    store = build_store(args.store_path)
    try:
        if all_sessions:
            reports = _verify_all(store)
            render.render_verify_all(reports, store_path=args.store_path)
            if not reports:
                return 0
            return 0 if all(r.all_passed for r in reports) else INTEGRITY_FAILURE_EXIT_CODE

        # Single-session path.
        report = _verify_single(store, session_id)
        render.render_verify(report, store_path=args.store_path)
        return 0 if report.all_passed else INTEGRITY_FAILURE_EXIT_CODE
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()


__all__ = ["INTEGRITY_FAILURE_EXIT_CODE", "cmd_verify"]
