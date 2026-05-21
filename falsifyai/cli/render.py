"""Plain-text terminal output for ``falsifyai run``, ``replay``, and ``diff``.

MVP scope: one row per case + a summary footer + the session id and store
path so the user can find their saved artifact. No colors, no boxes, no
JSON. Rich/colored output and ``--json`` land in Week 3 per
[plan.md section 22.1](../../plan.md).

The ``loaded_from`` parameter on ``render_session`` is what distinguishes
the replay path: when set, an extra header line indicates the user is
looking at a stored session rather than a fresh run. The detection of
legacy artifacts (pre-PR-11, no CI evidence) lives in this module too --
the artifact shape, not the consumer, determines what's renderable.

``render_diff`` is the diff CLI's render path (PR #14). It consumes a
``DiffReport`` (consumer-side dataclass from cli/diff.py) and prints a
compressed transition table: only rows where something changed are shown.
"""

import sys
from datetime import datetime
from typing import TYPE_CHECKING, TextIO

from falsifyai.replay.models import CaseResult, ReplayArtifact
from falsifyai.verdict.models import Verdict

if TYPE_CHECKING:
    # Type-only import to avoid a circular import at runtime: cli/diff.py
    # imports render. The DiffReport dataclass lives in diff.py because it
    # is a consumer-side structure, not part of the persisted artifact schema.
    from falsifyai.cli.diff import CaseTransition, DiffReport

# Exit codes mapped to the MVP 5 verdicts per plan.md section 16.1.
#   STABLE              -> 0  SUCCESS
#   FRAGILE             -> 1  DEGRADED
#   CONSISTENTLY_WRONG  -> 2  FAILURE
#   INVALID_EVAL        -> 2  FAILURE
#   INSUFFICIENT        -> 4  INSUFFICIENT
# Code 3 (ERROR) is reserved for infrastructure failures raised by the CLI
# layer before a verdict exists; code 5 (REGRESSION) and 6 (LOW_FALSIFIABILITY)
# land with the Week 2 features.
_EXIT_CODES: dict[Verdict, int] = {
    Verdict.STABLE: 0,
    Verdict.FRAGILE: 1,
    Verdict.CONSISTENTLY_WRONG: 2,
    Verdict.INVALID_EVAL: 2,
    Verdict.INSUFFICIENT: 4,
}


def exit_code_for(verdict: Verdict) -> int:
    """CI exit code for a session-level verdict."""
    return _EXIT_CODES[verdict]


def _is_legacy_case(case: CaseResult) -> bool:
    """Pre-PR-11 artifact heuristic: nonzero verdict_confidence but no CI evidence.

    The defaults from the dataclass extension (zero CI fields) trigger this
    only when the case was constructed without PR #11's resolver -- i.e., it
    was loaded from a pre-PR-11 replay store row. We require
    ``verdict_confidence > 0`` so an INSUFFICIENT case (all zeros, legitimately)
    doesn't get the legacy marker.
    """
    return (
        case.verdict_confidence > 0.0
        and case.stability == 0.0
        and case.stability_ci_high == 0.0
        and case.stability_ci_low == 0.0
    )


def render_session(
    artifact: ReplayArtifact,
    *,
    store_path: str,
    stream: TextIO | None = None,
    loaded_from: datetime | None = None,
) -> None:
    """Print one row per case, then a summary footer.

    Per-case row format:
        case: <id>  verdict: <V>  confidence: <p> (CI: <lo>-<hi>)  worst: <family>?

    When ``loaded_from`` is set (replay path), an extra header line is
    prepended indicating the session was loaded from the store.

    Legacy case detection: cases without CI evidence (pre-PR-11 artifacts)
    omit the misleading ``(CI: 0.00-0.00)`` and append ``(legacy)`` instead.
    """
    out = stream if stream is not None else sys.stdout

    if loaded_from is not None:
        out.write(
            f"Loaded session {artifact.session_id} · "
            f"created_at {loaded_from.isoformat()} from {store_path}\n"
        )

    for case in artifact.case_results:
        if _is_legacy_case(case):
            line = (
                f"case: {case.case_id}  verdict: {case.verdict.value.upper()}  "
                f"confidence: {case.verdict_confidence:.2f}  (legacy)"
            )
        else:
            line = (
                f"case: {case.case_id}  verdict: {case.verdict.value.upper()}  "
                f"confidence: {case.verdict_confidence:.2f} "
                f"(CI: {case.stability_ci_low:.2f}-{case.stability_ci_high:.2f})"
            )
            if case.verdict is Verdict.FRAGILE and case.worst_case_family:
                line += f"  worst: {case.worst_case_family}"
        out.write(line + "\n")
    out.write("=" * 65 + "\n")
    out.write(f"Session {artifact.session_id} -> {store_path}\n")
    sv = artifact.session_verdict
    out.write(
        f"{sv.case_count} case{'s' if sv.case_count != 1 else ''}, "
        f"verdict {sv.session_verdict.value.upper()}, "
        f"{sv.fragile_count} FRAGILE, "
        f"{sv.consistently_wrong_count} CONSISTENTLY_WRONG, "
        f"falsifiability {sv.falsifyai_falsifiability_score:.2f}\n"
    )


# ---------------------------------------------------------------------------
# Diff rendering (PR #14)
# ---------------------------------------------------------------------------


def _format_verdict_with_stability(verdict: Verdict | None, ci_low: float) -> str:
    """Format ``STABLE (0.92)`` or ``-`` if the case is absent on one side."""
    if verdict is None:
        return "-"
    return f"{verdict.value.upper()} ({ci_low:.2f})"


def _format_transition_row(t: "CaseTransition") -> str:
    """One row of the diff transition table.

    Format: ``case: <id>  baseline: <V> (n.nn)  candidate: <V> (n.nn)  <KIND>``
    """
    baseline_str = _format_verdict_with_stability(t.baseline_verdict, t.baseline_stability_ci_low)
    candidate_str = _format_verdict_with_stability(
        t.candidate_verdict, t.candidate_stability_ci_low
    )
    return (
        f"case: {t.case_id}  "
        f"baseline: {baseline_str}  "
        f"candidate: {candidate_str}  "
        f"{t.transition_kind.value.upper()}"
    )


def render_diff(
    report: "DiffReport",
    *,
    store_path: str,
    stream: TextIO | None = None,
) -> None:
    """Print a compressed transition table for two stored sessions.

    Only transitions != UNCHANGED are surfaced as rows. The summary footer
    always shows the full counts (unchanged + regressed + improved + ...).
    Evidence density: show what changed; report what didn't via counts only.
    """
    from falsifyai.cli.diff import TransitionKind

    out = stream if stream is not None else sys.stdout

    out.write(
        f"Diff: baseline {report.baseline_session_id} -> candidate {report.candidate_session_id}\n"
    )
    out.write(f"Store: {store_path}\n")
    if report.materialized_hash_mismatch:
        out.write(
            "note: materialized_hash differs between baseline and candidate; "
            "comparisons may not be apples-to-apples.\n"
        )
    out.write("=" * 65 + "\n")

    surfaced = [t for t in report.transitions if t.transition_kind is not TransitionKind.UNCHANGED]
    if not surfaced:
        out.write("(no transitions; all cases unchanged)\n")
    else:
        for t in surfaced:
            out.write(_format_transition_row(t) + "\n")

    out.write("=" * 65 + "\n")
    out.write(
        f"{report.regressed_count} regressed, "
        f"{report.improved_count} improved, "
        f"{report.unchanged_count} unchanged, "
        f"{report.other_change_count} other, "
        f"{report.added_count} added, "
        f"{report.removed_count} removed\n"
    )
