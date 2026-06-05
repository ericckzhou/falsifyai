"""``falsifyai matrix <session_id>...`` — cross-model reliability profiles.

Where ``diff`` compares two sessions case-by-case, ``matrix`` generalizes to
**N models x perturbation families**: one column per session (model run), one
row per perturbation family, each cell the model's *worst-case* stability in
that family. It answers "which model is robust to which kind of pressure?" at a
glance — the Reliability Profiles idea.

Pure consumer surface over preserved evidence (like ``history`` / ``diff``):

- **Read-only.** Reads each case's ``per_family_stability`` as recorded at run
  time. Never re-resolves; ``falsifyai.verdict.resolver`` is forbidden from this
  module's import graph (enforced by a meta-test).
- **Worst-case aggregation.** A model's stability for a family is the *minimum*
  across cases — consistent with the framework's worst-case stratified
  philosophy (plan.md §12). One weak case is not hidden by strong ones.
- **No re-derivation.** If a session never exercised a family, the cell is blank
  rather than guessed.
"""

import argparse
import contextlib
import sys
from dataclasses import dataclass, field
from typing import TextIO

from falsifyai.cli.errors import InfrastructureError
from falsifyai.replay.in_memory_store import InMemoryStore
from falsifyai.replay.models import ReplayArtifact
from falsifyai.replay.protocol import ReplayStore, SessionNotFoundError
from falsifyai.replay.sqlite_store import SQLiteStore


def _build_store(store_path: str) -> ReplayStore:
    """Mirror the store selection used by run/replay/inspect/diff/history."""
    if store_path == ":memory:":
        return InMemoryStore()
    return SQLiteStore(store_path)


@dataclass(frozen=True)
class MatrixColumn:
    """One session's column header: a short label, model, id, session verdict."""

    label: str  # M1, M2, ...
    session_id: str
    model: str  # provider:model
    session_verdict: str


@dataclass(frozen=True)
class MatrixReport:
    """The computed N-models x families matrix."""

    families: list[str]
    columns: list[MatrixColumn]
    # (family, session_id) -> worst-case stability, or None if family absent.
    cells: dict[tuple[str, str], float | None] = field(default_factory=dict)


def _worst_per_family(artifact: ReplayArtifact) -> dict[str, float]:
    """Minimum per-family stability across all cases in one session."""
    worst: dict[str, float] = {}
    for case in artifact.case_results:
        for family, stability in case.per_family_stability.items():
            if family not in worst or stability < worst[family]:
                worst[family] = stability
    return worst


def compute_matrix(artifacts: list[ReplayArtifact]) -> MatrixReport:
    """Build the reliability matrix from N loaded artifacts (column order preserved)."""
    columns: list[MatrixColumn] = []
    per_session_worst: dict[str, dict[str, float]] = {}
    families: set[str] = set()

    for i, artifact in enumerate(artifacts, start=1):
        model = artifact.materialized.model
        columns.append(
            MatrixColumn(
                label=f"M{i}",
                session_id=artifact.session_id,
                model=f"{model.provider}:{model.model}",
                session_verdict=artifact.session_verdict.session_verdict.value.upper(),
            )
        )
        worst = _worst_per_family(artifact)
        per_session_worst[artifact.session_id] = worst
        families.update(worst)

    family_list = sorted(families)
    cells: dict[tuple[str, str], float | None] = {}
    for family in family_list:
        for col in columns:
            cells[(family, col.session_id)] = per_session_worst[col.session_id].get(family)

    return MatrixReport(families=family_list, columns=columns, cells=cells)


def _render(report: MatrixReport, *, stream: TextIO) -> None:
    n_models = len(report.columns)
    n_families = len(report.families)
    stream.write(f"falsifyai matrix | {n_models} model{'s' if n_models != 1 else ''} x ")
    stream.write(f"{n_families} famil{'ies' if n_families != 1 else 'y'}\n")
    stream.write("=" * 70 + "\n")

    family_col_width = max([len("family"), *(len(f) for f in report.families)])
    header = "family".ljust(family_col_width)
    for col in report.columns:
        header += "  " + col.label.rjust(8)
    stream.write(header + "\n")

    for family in report.families:
        row = family.ljust(family_col_width)
        for col in report.columns:
            value = report.cells[(family, col.session_id)]
            cell = "-" if value is None else f"{value:.2f}"
            row += "  " + cell.rjust(8)
        stream.write(row + "\n")

    stream.write("=" * 70 + "\n")
    stream.write("legend:\n")
    for col in report.columns:
        stream.write(
            f"  {col.label} = {col.model}  ({col.session_id[:8]})  {col.session_verdict}\n"
        )


def cmd_matrix(args: argparse.Namespace) -> int:
    """Entry point for the ``matrix`` subcommand. Returns an exit code.

    Exit semantics: 0 on render success (informational, like ``history``);
    3 (ERROR) if a session id is not found in the store.
    """
    store = _build_store(args.store_path)
    stream = sys.stdout
    with contextlib.suppress(AttributeError, ValueError):
        stream.reconfigure(errors="backslashreplace")  # type: ignore[union-attr]

    try:
        artifacts: list[ReplayArtifact] = []
        for session_id in args.session_ids:
            try:
                artifacts.append(store.load_session(session_id))
            except SessionNotFoundError as exc:
                raise InfrastructureError(
                    f"session {session_id!r} not found in store {args.store_path}"
                ) from exc
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()

    report = compute_matrix(artifacts)
    _render(report, stream=stream)
    return 0


__all__ = ["cmd_matrix", "compute_matrix", "MatrixReport", "MatrixColumn"]
