"""``falsifyai replay <session_id>`` -- read-only consumer surface.

Loads a stored ``ReplayArtifact`` from the configured ``ReplayStore`` and
re-renders it via the existing ``cli/render.render_session``. No model
calls, no resolver invocation, no perturbations -- pure inspection of a
past run.

Invariants:

- ``cmd_replay`` is strictly read-only. It never modifies the stored
  artifact. The verdict displayed is the verdict the resolver assigned at
  ``run`` time -- not a re-resolution under the current resolver.
- Exit codes mirror ``run``: the verdict-derived exit code lets CI use
  ``falsifyai replay <known-good-id>`` as a regression gate.
- ``--store-path :memory:`` is supported for symmetry with ``run``, even
  though ``InMemoryStore`` is empty on every fresh process. Failure mode
  is loud: ``SessionNotFoundError`` -> exit 3.
"""

import argparse

from falsifyai.cli import render
from falsifyai.cli.errors import InfrastructureError
from falsifyai.replay.in_memory_store import InMemoryStore
from falsifyai.replay.protocol import ReplayStore, SessionNotFoundError
from falsifyai.replay.sqlite_store import SQLiteStore


def _build_store(store_path: str) -> ReplayStore:
    """Mirror cli/run.py's store selection: ``:memory:`` -> InMemoryStore."""
    if store_path == ":memory:":
        return InMemoryStore()
    return SQLiteStore(store_path)


def _resolve_target_session_id(store: ReplayStore, args: argparse.Namespace) -> str:
    """Pick the session_id to load: explicit, or newest if ``--latest``."""
    if args.latest:
        if args.session_id is not None:
            # argparse should already reject this; defensive guard.
            raise InfrastructureError("--latest is mutually exclusive with a positional session_id")
        newest = next(iter(store.query_sessions(limit=1)), None)
        if newest is None:
            raise InfrastructureError("no sessions in store; cannot resolve --latest")
        return newest.session_id

    if args.session_id is None:
        raise InfrastructureError("session_id is required (or pass --latest)")
    return args.session_id


def cmd_replay(args: argparse.Namespace) -> int:
    """Entry point for the ``replay`` subcommand. Returns an exit code."""
    store = _build_store(args.store_path)
    try:
        session_id = _resolve_target_session_id(store, args)
        try:
            artifact = store.load_session(session_id)
        except SessionNotFoundError as exc:
            raise InfrastructureError(f"session not found: {session_id}") from exc
    finally:
        # InMemoryStore has no close(); SQLiteStore does.
        close = getattr(store, "close", None)
        if callable(close):
            close()

    render.render_session(
        artifact,
        store_path=args.store_path,
        loaded_from=artifact.created_at,
    )

    return render.exit_code_for(artifact.session_verdict.session_verdict)


__all__ = ["cmd_replay"]
