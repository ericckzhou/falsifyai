"""``falsifyai history <case_id>`` — temporal view of one case across sessions.

Compresses how a single case has behaved across saved sessions into one
screen: one row per session, newest-first by default. Pure consumer
surface over preserved evidence — reads ``case.verdict`` from each
artifact, never re-resolves, never aggregates.

Invariants (load-bearing — see PR-24 plan §12 for context):

- **Read-only.** Verdicts shown are the verdicts the resolver assigned at
  run time. ``falsifyai.verdict.resolver`` is forbidden from this
  module's import graph; ``test_history_does_not_import_resolver``
  enforces it via ``importlib`` introspection.
- **No aggregation.** No averages, no trend indicators, no
  "improving/regressing" labels. The reader sees raw rows and computes
  whatever inferences they want.
- **No row suppression.** Every matching session shows (decision Z1).
  Compression comes from per-row density, not from omission.
- **No spec_hash filter** (decision X1). The case identity transcends
  spec evolution — that's what makes the timeline interesting.
- **Newest-first** (decision Y1). Matches the ``query_sessions`` default.
- **Exit code 0 on render success** (decision E1). History is
  informational; verdict-derived exit codes are for ``replay`` and
  ``diff``. Code 3 (ERROR) only for infrastructure failures
  (case_id-not-found, malformed evidence).
- **Malformed evidence surfaces explicitly** (decision G1). If an
  artifact contains the same case_id twice, render a `<malformed>`
  marker row naming the issue. Don't silently pick one.
"""

import argparse
import contextlib
import sys
from typing import TextIO

from falsifyai.cli import render
from falsifyai.cli.errors import InfrastructureError
from falsifyai.replay.in_memory_store import InMemoryStore
from falsifyai.replay.models import CaseResult, ReplayArtifact
from falsifyai.replay.protocol import ReplayStore
from falsifyai.replay.sqlite_store import SQLiteStore
from falsifyai.verdict.models import Verdict


def _build_store(store_path: str) -> ReplayStore:
    """Mirror cli/run.py / cli/replay.py / cli/inspect.py store selection."""
    if store_path == ":memory:":
        return InMemoryStore()
    return SQLiteStore(store_path)


def _matching_cases(artifact: ReplayArtifact, case_id: str) -> list[CaseResult]:
    """Return all CaseResults in an artifact whose case_id matches.

    In a well-formed artifact this is 0 or 1. Returning multiple signals
    malformed evidence (decision G1).
    """
    return [c for c in artifact.case_results if c.case_id == case_id]


def _render_row(artifact: ReplayArtifact, case: CaseResult, *, stream: TextIO) -> None:
    """One per-session row. D1 columns: session prefix · created_at · verdict · CI · worst."""
    sid_short = artifact.session_id[:8]
    created_at = artifact.created_at.isoformat()
    verdict_str = case.verdict.value.upper()
    is_legacy = render._is_legacy_case(case)
    if is_legacy:
        ci_str = "(legacy)"
    else:
        ci_str = (
            f"{case.verdict_confidence:.2f} "
            f"(CI: {case.stability_ci_low:.2f}-{case.stability_ci_high:.2f})"
        )
    line = f"  {sid_short}  {created_at}  {verdict_str}  {ci_str}"
    if case.verdict is Verdict.FRAGILE and case.worst_case_family:
        line += f"  worst: {case.worst_case_family}"
    stream.write(line + "\n")


def _render_malformed_row(
    artifact: ReplayArtifact, case_id: str, match_count: int, *, stream: TextIO
) -> None:
    """G1: surface duplicate-case-id evidence explicitly."""
    sid_short = artifact.session_id[:8]
    created_at = artifact.created_at.isoformat()
    stream.write(
        f"  {sid_short}  {created_at}  <malformed: {match_count} matches for case_id {case_id!r}>\n"
    )


def cmd_history(args: argparse.Namespace) -> int:
    """Entry point for the ``history`` subcommand. Returns an exit code.

    Exit semantics (E1):
        0 — render succeeded (regardless of verdict mix)
        3 — case_id matched zero sessions, OR malformed evidence was found
    """
    case_id = args.case_id
    # F1: --limit 0 means unlimited. The store's API requires a concrete
    # int; sys.maxsize is the canonical "as many as you've got" expression.
    effective_limit = sys.maxsize if args.limit == 0 else args.limit

    store = _build_store(args.store_path)
    matched_any = False
    encountered_malformed = False
    stream = sys.stdout

    # cp1252-safe rendering: same pattern as inspect (PR-19). Defensive
    # against model-emitted unicode in future column additions. Falls
    # back silently on streams that don't support reconfigure (capsys).
    with contextlib.suppress(AttributeError, ValueError):
        stream.reconfigure(errors="backslashreplace")  # type: ignore[union-attr]

    try:
        # Header. ASCII-only separator so the output is identical across
        # terminal encodings (no cp1252 surprises).
        stream.write(f"falsifyai history | case: {case_id}\n")
        stream.write("=" * 65 + "\n")

        # Single pass: store yields newest-first per Y1.
        rows_rendered = 0
        for artifact in store.query_sessions(case_id=case_id, limit=effective_limit):
            matched_any = True
            cases = _matching_cases(artifact, case_id)
            if len(cases) > 1:
                # G1: malformed evidence — surface explicitly, exit 3 at end
                encountered_malformed = True
                _render_malformed_row(artifact, case_id, len(cases), stream=stream)
            elif len(cases) == 1:
                _render_row(artifact, cases[0], stream=stream)
            else:
                # Defensive: query_sessions matched the session but the
                # artifact has no row for this case_id. Shouldn't happen
                # given the case_results table denormalization, but if it
                # ever does, name it rather than skip silently.
                encountered_malformed = True
                _render_malformed_row(artifact, case_id, 0, stream=stream)
            rows_rendered += 1
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()

    if not matched_any:
        raise InfrastructureError(
            f"no sessions found for case_id {case_id!r} in store {args.store_path}"
        )

    # Footer
    stream.write("=" * 65 + "\n")
    suffix = ""
    if args.limit != 0 and rows_rendered >= args.limit:
        suffix = f" (showing newest {rows_rendered}; rerun with --limit 0 for all)"
    stream.write(f"{rows_rendered} session{'s' if rows_rendered != 1 else ''} matched{suffix}\n")

    if encountered_malformed:
        # G1: scripts see exit 3 so the anomaly isn't silent in CI pipelines
        return 3
    return 0


__all__ = ["cmd_history"]
