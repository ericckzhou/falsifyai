"""``falsifyai timeline <case_id>`` — longitudinal robustness trend for one case.

This is the **inference counterpart** to ``history``. ``history`` shows raw,
newest-first rows and deliberately refuses to aggregate, average, or label
trends — it keeps verdicts defensible as preserved evidence. ``timeline`` does
the opposite job on purpose: it orders sessions chronologically, draws the
``stability_ci_low`` trend as a sparkline, and flags **regression points** where
a case's verdict class downgraded between consecutive runs.

The two coexist cleanly: reach for ``history`` to read the evidence, ``timeline``
to read the story it tells.

- **Read-only / no re-resolution.** Verdicts and stabilities are the ones
  recorded at run time. ``falsifyai.verdict.resolver`` is forbidden from this
  module's import graph (enforced by a meta-test).
- **Regression = verdict-class downgrade**, defined identically to ``diff``
  (``_classify_transition``) so the two commands never disagree.
- **Exit 5 (REGRESSION)** if any consecutive downgrade is found, so the trend is
  CI-gateable; 0 otherwise; 3 on infrastructure failure.
"""

import argparse
import contextlib
import sys
from dataclasses import dataclass, field
from typing import TextIO

from falsifyai.cli.diff import TransitionKind, _classify_transition
from falsifyai.cli.errors import InfrastructureError
from falsifyai.replay.models import CaseResult, ReplayArtifact
from falsifyai.replay.registry import build_store
from falsifyai.verdict.models import Verdict

# ASCII sparkline ramp (10 levels), cp1252-safe — no unicode block glyphs.
_SPARK = " .:-=+*#%@"


@dataclass(frozen=True)
class TimelinePoint:
    """One session's robustness reading for the traced case (chronological)."""

    session_id: str
    created_at: str
    stability_ci_low: float
    verdict: Verdict
    regressed_from_prev: bool


@dataclass(frozen=True)
class TimelineReport:
    points: list[TimelinePoint] = field(default_factory=list)

    @property
    def regression_count(self) -> int:
        return sum(1 for p in self.points if p.regressed_from_prev)

    @property
    def has_regression(self) -> bool:
        return self.regression_count > 0


def _first_case(artifact: ReplayArtifact, case_id: str) -> CaseResult | None:
    for case in artifact.case_results:
        if case.case_id == case_id:
            return case
    return None


def compute_timeline(chronological: list[tuple[ReplayArtifact, CaseResult]]) -> TimelineReport:
    """Build the timeline from (artifact, case) pairs ordered oldest -> newest."""
    points: list[TimelinePoint] = []
    prev_verdict: Verdict | None = None
    for artifact, case in chronological:
        regressed = (
            prev_verdict is not None
            and _classify_transition(prev_verdict, case.verdict) is TransitionKind.REGRESSED
        )
        points.append(
            TimelinePoint(
                session_id=artifact.session_id,
                created_at=artifact.created_at.isoformat(),
                stability_ci_low=case.stability_ci_low,
                verdict=case.verdict,
                regressed_from_prev=regressed,
            )
        )
        prev_verdict = case.verdict
    return TimelineReport(points=points)


def _sparkline(values: list[float]) -> str:
    chars = []
    for v in values:
        clamped = min(1.0, max(0.0, v))
        idx = min(len(_SPARK) - 1, int(clamped * len(_SPARK)))
        chars.append(_SPARK[idx])
    return "".join(chars)


def _render(report: TimelineReport, case_id: str, *, stream: TextIO) -> None:
    stream.write(f"falsifyai timeline | case: {case_id}\n")
    stream.write("=" * 65 + "\n")

    if report.points:
        stream.write("  trend (CI low, oldest->newest): ")
        stream.write(f"[{_sparkline([p.stability_ci_low for p in report.points])}]\n\n")

    for p in report.points:
        marker = "  <-- REGRESSION" if p.regressed_from_prev else ""
        stream.write(
            f"  {p.session_id[:8]}  {p.created_at}  "
            f"CIlow={p.stability_ci_low:.2f}  {p.verdict.value.upper()}{marker}\n"
        )

    stream.write("=" * 65 + "\n")
    n = len(report.points)
    rc = report.regression_count
    stream.write(
        f"{n} session{'s' if n != 1 else ''} | {rc} regression{'s' if rc != 1 else ''} detected\n"
    )


def cmd_timeline(args: argparse.Namespace) -> int:
    """Entry point for the ``timeline`` subcommand. Returns an exit code.

    Exit: 5 (REGRESSION) if any consecutive verdict downgrade; 0 otherwise;
    3 (ERROR) if the case_id matched zero sessions.
    """
    case_id = args.case_id
    effective_limit = sys.maxsize if args.limit == 0 else args.limit
    store = build_store(args.store_path)
    stream = sys.stdout
    with contextlib.suppress(AttributeError, ValueError):
        stream.reconfigure(errors="backslashreplace")  # type: ignore[union-attr]

    try:
        # query_sessions yields newest-first; reverse to chronological.
        newest_first = list(store.query_sessions(case_id=case_id, limit=effective_limit))
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()

    if not newest_first:
        raise InfrastructureError(
            f"no sessions found for case_id {case_id!r} in store {args.store_path}"
        )

    chronological: list[tuple[ReplayArtifact, CaseResult]] = []
    for artifact in reversed(newest_first):
        case = _first_case(artifact, case_id)
        if case is not None:
            chronological.append((artifact, case))

    report = compute_timeline(chronological)
    _render(report, case_id, stream=stream)
    return 5 if report.has_regression else 0


__all__ = ["cmd_timeline", "compute_timeline", "TimelineReport", "TimelinePoint"]
