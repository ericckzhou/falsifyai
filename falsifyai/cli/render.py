"""Plain-text terminal output for the human-readable CLI surfaces.

Deliberately plain text -- no colors, no boxes, no JSON. The discipline is
evidence density, not presentation: one row per case + a summary footer +
the session id and store path so the user can find their saved artifact.
This module renders ``run`` / ``replay`` (``render_session``), ``diff``
(``render_diff``), ``verify`` (``render_verify`` / ``render_verify_all``),
and ``export`` (``render_export`` / ``render_export_refusal``).

The ``loaded_from`` parameter on ``render_session`` is what distinguishes
the replay path: when set, an extra header line indicates the user is
looking at a stored session rather than a fresh run. The detection of
legacy artifacts (no CI evidence preserved) lives in this module too --
the artifact shape, not the consumer, determines what's renderable.

``render_diff`` consumes a ``DiffReport`` (consumer-side dataclass from
cli/diff.py) and prints a compressed transition table: only rows where
something changed are shown.
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
    from pathlib import Path

    from falsifyai.bundle.writer import BundleManifest
    from falsifyai.cli.diff import CaseTransition, DiffReport
    from falsifyai.integrity.checks import IntegrityReport

# Session verdict -> CI exit code, per plan.md section 16.1. The full 9-verdict
# taxonomy collapses onto four buckets here (see the grouped dict below):
#   0 SUCCESS  ·  1 DEGRADED  ·  2 FAILURE  ·  4 INSUFFICIENT.
# Code 3 (ERROR) is reserved for infrastructure failures raised by the CLI layer
# before a verdict exists; codes 5 (REGRESSION) and 6 (LOW_FALSIFIABILITY) are
# emitted by other surfaces (e.g. `falsifyai diff`), not by this verdict map.
_EXIT_CODES: dict[Verdict, int] = {
    # SUCCESS (0): high stability, optionally grounded.
    Verdict.INFORMATION_PRESENT: 0,
    Verdict.STABLE: 0,
    # DEGRADED (1): instability or thin/empty evidence -- reliability not refuted
    # outright, but the claim is weakened.
    Verdict.FRAGILE: 1,
    Verdict.AMBIGUOUS: 1,
    Verdict.INFORMATION_NULL: 1,
    # FAILURE (2): a known-wrong, targeted, or broken-eval result.
    Verdict.CONSISTENTLY_WRONG: 2,
    Verdict.ADVERSARIALLY_VULNERABLE: 2,
    Verdict.INVALID_EVAL: 2,
    # INSUFFICIENT (4): not enough structure to judge.
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


# Verdicts decided by the resolver's instability band (resolver.py: the
# worst-case stability CI lower bound fell below the stable bar). For these,
# ``verdict_confidence`` IS that CI *floor* -- it collapses toward 0.00 exactly
# when the case is most broken and best-supported. Labeling that "confidence"
# inverts its meaning (a severe, well-backed verdict reads as "low confidence"),
# so the consumer surface names it for what it is. Verdict logic and the stored
# field are unchanged -- this is presentation only. See
# docs/case-studies/05-confidence-floor-inversion.md.
_INSTABILITY_BAND: frozenset[Verdict] = frozenset(
    {Verdict.ADVERSARIALLY_VULNERABLE, Verdict.FRAGILE, Verdict.AMBIGUOUS}
)


def _metric_label(case: CaseResult) -> str:
    """Band-aware label for ``verdict_confidence``.

    Stable-band verdicts read ``ci_low`` as genuine confidence-in-stability and
    keep the ``confidence:`` label. Instability-band verdicts read the same
    number as a stability *floor*; relabeling it keeps the number from inverting
    its meaning for the reader.
    """
    if case.verdict in _INSTABILITY_BAND:
        return f"stability floor: {case.verdict_confidence:.2f}"
    return f"confidence: {case.verdict_confidence:.2f}"


def render_session(
    artifact: ReplayArtifact,
    *,
    store_path: str,
    stream: TextIO | None = None,
    loaded_from: datetime | None = None,
) -> None:
    """Print one row per case, then a summary footer.

    Per-case row format:
        case: <id>  verdict: <V>  <metric>: <p> (CI: <lo>-<hi>)  worst: <family>?

    ``<metric>`` is band-aware (see ``_metric_label``): stable-band verdicts show
    ``confidence``; instability-band verdicts (ADVERSARIALLY_VULNERABLE / FRAGILE
    / AMBIGUOUS) show ``stability floor`` so the same ``verdict_confidence`` value
    does not read as low confidence when it actually signals high severity.

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
                f"{_metric_label(case)}  (legacy)"
            )
        else:
            line = (
                f"case: {case.case_id}  verdict: {case.verdict.value.upper()}  "
                f"{_metric_label(case)} "
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


# Confidence delta below this absolute value is rendering noise; shown as STABLE.
_TIMELINE_NOISE_FLOOR: float = 0.01


def _timeline_marker(t: "CaseTransition") -> str:
    """Per-row marker for --show-timeline rendering.

    For non-UNCHANGED transitions the existing kind label is reused.
    For UNCHANGED transitions a direction label is computed from the
    confidence delta so readers can see cases trending without having
    crossed a verdict-class boundary.
    """
    from falsifyai.cli.diff import TransitionKind

    if t.transition_kind is not TransitionKind.UNCHANGED:
        return t.transition_kind.value.upper()

    delta = t.candidate_stability_ci_low - t.baseline_stability_ci_low
    if delta <= -_TIMELINE_NOISE_FLOOR:
        return (
            f"DECLINED {t.baseline_stability_ci_low:.2f}"
            f"->{t.candidate_stability_ci_low:.2f}"
            f" ({delta:+.2f})"
        )
    if delta >= _TIMELINE_NOISE_FLOOR:
        return (
            f"RECOVERED {t.baseline_stability_ci_low:.2f}"
            f"->{t.candidate_stability_ci_low:.2f}"
            f" ({delta:+.2f})"
        )
    return "STABLE"


def _format_transition_row_timeline(t: "CaseTransition") -> str:
    """One row for --show-timeline: same shape as default but with a timeline marker."""
    baseline_str = _format_verdict_with_stability(t.baseline_verdict, t.baseline_stability_ci_low)
    candidate_str = _format_verdict_with_stability(
        t.candidate_verdict, t.candidate_stability_ci_low
    )
    return (
        f"case: {t.case_id}  "
        f"baseline: {baseline_str}  "
        f"candidate: {candidate_str}  "
        f"{_timeline_marker(t)}"
    )


def render_diff(
    report: "DiffReport",
    *,
    store_path: str,
    stream: TextIO | None = None,
    show_timeline: bool = False,
) -> None:
    """Print a transition table for two stored sessions.

    Default (no flags): only transitions != UNCHANGED are surfaced as rows.
    The summary footer always shows the full counts.

    With ``show_timeline=True``: every case is rendered with a per-row
    direction marker (REGRESSED, IMPROVED, DECLINED, RECOVERED, STABLE).
    Exit code is unaffected by this flag.
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

    if show_timeline:
        if not report.transitions:
            out.write("(no cases)\n")
        else:
            for t in report.transitions:
                out.write(_format_transition_row_timeline(t) + "\n")
    else:
        surfaced = [
            t for t in report.transitions if t.transition_kind is not TransitionKind.UNCHANGED
        ]
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


# ---------------------------------------------------------------------------
# Verify rendering (PR-31)
# ---------------------------------------------------------------------------


_CHECK_NAME_WIDTH = 38  # padding for the 8 check names so status columns align


def _format_check_row(name: str, status: str, detail: str) -> str:
    return f"check: {name:<{_CHECK_NAME_WIDTH}} status: {status:<4}  detail: {detail}"


def render_verify(
    report: "IntegrityReport",
    *,
    store_path: str,
    stream: TextIO | None = None,
) -> None:
    """Render one integrity report: header, per-check rows, summary footer."""
    from falsifyai.integrity.checks import CheckStatus

    out = stream if stream is not None else sys.stdout

    out.write(f"session: {report.session_id}\n")
    for r in report.results:
        out.write(_format_check_row(r.name, r.status.value.upper(), r.detail) + "\n")
    out.write("=" * 65 + "\n")
    passed = sum(1 for r in report.results if r.status is CheckStatus.PASS)
    failed = sum(1 for r in report.results if r.status is CheckStatus.FAIL)
    out.write(
        f"{len(report.results)} checks, {passed} passed, {failed} failed; "
        f"session {report.session_id}; store {store_path}\n"
    )


def render_verify_all(
    reports: list["IntegrityReport"],
    *,
    store_path: str,
    stream: TextIO | None = None,
) -> None:
    """Render multiple integrity reports as ``--all`` output.

    Per-session block (header, checks, mini-footer) separated by dashes;
    final aggregate footer with totals.
    """
    from falsifyai.integrity.checks import CheckStatus

    out = stream if stream is not None else sys.stdout

    if not reports:
        out.write("(no sessions in store)\n")
        out.write(f"Store: {store_path}\n")
        return

    for i, report in enumerate(reports):
        if i > 0:
            out.write("-" * 65 + "\n")
        out.write(f"session: {report.session_id}\n")
        for r in report.results:
            out.write(_format_check_row(r.name, r.status.value.upper(), r.detail) + "\n")
        passed = sum(1 for r in report.results if r.status is CheckStatus.PASS)
        failed = sum(1 for r in report.results if r.status is CheckStatus.FAIL)
        out.write(f"{len(report.results)} checks, {passed} passed, {failed} failed\n")

    total_checks = sum(len(r.results) for r in reports)
    total_passed = sum(1 for r in reports for c in r.results if c.status is CheckStatus.PASS)
    total_failed = total_checks - total_passed
    out.write("=" * 65 + "\n")
    out.write(
        f"{len(reports)} sessions; "
        f"total {total_checks} checks, {total_passed} passed, {total_failed} failed; "
        f"store {store_path}\n"
    )


# ---------------------------------------------------------------------------
# Export rendering (PR-32)
# ---------------------------------------------------------------------------


def render_export(
    manifest: "BundleManifest",
    *,
    output_path: "Path",
    stream: TextIO | None = None,
) -> None:
    """Render the summary after a successful bundle write.

    Single-section output: bundle path, bundle id, session id, file count,
    total bytes, integrity status. No multi-file table — ``manifest.json``
    is the canonical machine-readable record.
    """
    out = stream if stream is not None else sys.stdout
    total_bytes = sum(e.size_bytes for e in manifest.files)
    status = manifest.pre_export_integrity["status"]
    protest_marker = " (UNDER PROTEST)" if manifest.exported_under_protest else ""
    out.write(f"Bundle: {output_path}\n")
    out.write(f"bundle_id: {manifest.bundle_id}\n")
    out.write(f"session_id: {manifest.session_id}\n")
    out.write(f"exported_at: {manifest.exported_at}\n")
    out.write(f"files: {len(manifest.files)} (total {total_bytes} bytes)\n")
    out.write(f"integrity: {status}{protest_marker}\n")


def render_export_refusal(
    report: "IntegrityReport",
    *,
    session_id: str,
    output_path: "Path",
    stream: TextIO | None = None,
) -> None:
    """Render the refusal message when integrity fails and --allow-corrupted is off."""
    from falsifyai.integrity.checks import CheckStatus

    out = stream if stream is not None else sys.stdout
    failed = [r.name for r in report.results if r.status is CheckStatus.FAIL]
    out.write(
        f"refusing to export: session {session_id} failed {len(failed)} integrity check(s): "
        f"{', '.join(failed)}\n"
    )
    out.write(f"no bundle written to {output_path}\n")
    out.write("re-run with --allow-corrupted to write the bundle anyway (NOT WORM-suitable)\n")
