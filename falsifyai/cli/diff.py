"""``falsifyai diff <baseline> <candidate>`` -- the launch wedge.

Loads two stored ``ReplayArtifact``s, compares them case-by-case, surfaces
verdict transitions in a compressed table, and exits **code 5 (REGRESSION)**
if any case regressed.

This is the differentiator per [plan.md §22.1](../../plan.md). Competitors
match an engine that runs perturbations; they do not flag model-migration
regressions with a single command.

**Invariants:**

- ``cmd_diff`` is strictly read-only. Never modifies either artifact.
- The diff does NOT re-resolve verdicts under the current resolver. The
  verdicts compared are the ones assigned at each ``run`` time. Diff is a
  consumer of already-resolved artifacts; the resolver stays untouched.
- Regression criterion is **verdict-class downgrade only**, ranked over the
  8-verdict quality ladder (``_QUALITY_RANK``): a move to a worse rank is a
  regression (e.g. STABLE -> FRAGILE, FRAGILE -> ADVERSARIALLY_VULNERABLE,
  INFORMATION_PRESENT -> STABLE). No thresholds, no per-stability deltas as
  regression signals. Predictable by design.
- Cases present in only one side are surfaced as ADDED / REMOVED but do NOT
  trigger exit 5. Specs evolve legitimately.
"""

import argparse
from dataclasses import dataclass
from enum import Enum

from falsifyai.cli import render
from falsifyai.cli.errors import InfrastructureError
from falsifyai.replay.models import ReplayArtifact
from falsifyai.replay.protocol import ReplayStore, SessionNotFoundError
from falsifyai.replay.registry import build_store
from falsifyai.verdict.models import Verdict

# Named thresholds for strict-mode detection (plan decisions B1 and D1).
# Intentionally not runtime-configurable: predictability over flexibility.
STRICT_CONFIDENCE_DROP_THRESHOLD: float = 0.10
LOW_FALSIFIABILITY_THRESHOLD: float = 0.50


class TransitionKind(Enum):
    """How a case's verdict changed between baseline and candidate."""

    UNCHANGED = "unchanged"
    IMPROVED = "improved"
    REGRESSED = "regressed"
    OTHER_CHANGE = "other_change"  # informational; not a regression
    ADDED = "added"  # in candidate only
    REMOVED = "removed"  # in baseline only


@dataclass(frozen=True)
class CaseTransition:
    """One row in the diff: how case <case_id>'s verdict changed."""

    case_id: str
    baseline_verdict: Verdict | None  # None if ADDED
    candidate_verdict: Verdict | None  # None if REMOVED
    baseline_stability_ci_low: float
    candidate_stability_ci_low: float
    transition_kind: TransitionKind


@dataclass(frozen=True)
class DiffReport:
    """Compressed summary of a diff between two ReplayArtifacts."""

    baseline_session_id: str
    candidate_session_id: str
    materialized_hash_mismatch: bool
    transitions: list[CaseTransition]
    regressed_count: int
    improved_count: int
    unchanged_count: int
    other_change_count: int
    added_count: int
    removed_count: int


# ---------------------------------------------------------------------------
# Transition classification
# ---------------------------------------------------------------------------


# Quality rank over the 8-verdict taxonomy (lower = better). A move to a higher
# rank is a REGRESSION; to a lower rank, an IMPROVEMENT; a tie (e.g. AMBIGUOUS vs
# INFORMATION_NULL, both "degraded") is OTHER_CHANGE -- not a clear up or down.
#
# The two cross-cutting meta-verdicts are intentionally OFF the ladder:
#   - INVALID_EVAL: a broken eval is not a point on the quality axis.
#   - INSUFFICIENT: "couldn't judge" -- handled asymmetrically below (recovering
#     FROM it to a positive verdict is an improvement, but degrading INTO it is
#     informational, not a regression).
_QUALITY_RANK: dict[Verdict, int] = {
    Verdict.INFORMATION_PRESENT: 0,
    Verdict.STABLE: 1,
    Verdict.AMBIGUOUS: 2,
    Verdict.INFORMATION_NULL: 2,
    Verdict.FRAGILE: 3,
    Verdict.ADVERSARIALLY_VULNERABLE: 4,
    Verdict.CONSISTENTLY_WRONG: 4,
}

# Confident-positive verdicts: recovering to one of these from INSUFFICIENT counts
# as an improvement (the eval went from "couldn't judge" to a clean result).
_POSITIVE_VERDICTS: frozenset[Verdict] = frozenset({Verdict.STABLE, Verdict.INFORMATION_PRESENT})


def _classify_transition(baseline: Verdict, candidate: Verdict) -> TransitionKind:
    """Decide what kind of transition this verdict-pair represents.

    Ranked verdicts compare by ``_QUALITY_RANK``: worse rank -> REGRESSED, better
    rank -> IMPROVED, tie -> OTHER_CHANGE. Recovering from INSUFFICIENT to a
    positive verdict is IMPROVED. Anything else (degrading into INSUFFICIENT, or
    any transition touching INVALID_EVAL) is OTHER_CHANGE -- informational, not a
    regression.
    """
    if baseline is candidate:
        return TransitionKind.UNCHANGED
    base_rank = _QUALITY_RANK.get(baseline)
    cand_rank = _QUALITY_RANK.get(candidate)
    if base_rank is not None and cand_rank is not None:
        if cand_rank > base_rank:
            return TransitionKind.REGRESSED
        if cand_rank < base_rank:
            return TransitionKind.IMPROVED
        return TransitionKind.OTHER_CHANGE
    # Recovered from "couldn't judge" to a clean positive verdict.
    if baseline is Verdict.INSUFFICIENT and candidate in _POSITIVE_VERDICTS:
        return TransitionKind.IMPROVED
    return TransitionKind.OTHER_CHANGE


def compute_diff(baseline: ReplayArtifact, candidate: ReplayArtifact) -> DiffReport:
    """Pure function: compare two artifacts case-by-case, produce a DiffReport.

    Cases are matched by ``case_id``. Cases in only one side are recorded as
    ADDED / REMOVED. The regression criterion is verdict-class downgrade
    per ``_classify_transition``.
    """
    baseline_cases = {c.case_id: c for c in baseline.case_results}
    candidate_cases = {c.case_id: c for c in candidate.case_results}

    all_case_ids = sorted(set(baseline_cases) | set(candidate_cases))
    transitions: list[CaseTransition] = []
    regressed = improved = unchanged = other_change = added = removed = 0

    for case_id in all_case_ids:
        b = baseline_cases.get(case_id)
        c = candidate_cases.get(case_id)
        if b is None:
            transitions.append(
                CaseTransition(
                    case_id=case_id,
                    baseline_verdict=None,
                    candidate_verdict=c.verdict,
                    baseline_stability_ci_low=0.0,
                    candidate_stability_ci_low=c.stability_ci_low,
                    transition_kind=TransitionKind.ADDED,
                )
            )
            added += 1
            continue
        if c is None:
            transitions.append(
                CaseTransition(
                    case_id=case_id,
                    baseline_verdict=b.verdict,
                    candidate_verdict=None,
                    baseline_stability_ci_low=b.stability_ci_low,
                    candidate_stability_ci_low=0.0,
                    transition_kind=TransitionKind.REMOVED,
                )
            )
            removed += 1
            continue
        kind = _classify_transition(b.verdict, c.verdict)
        transitions.append(
            CaseTransition(
                case_id=case_id,
                baseline_verdict=b.verdict,
                candidate_verdict=c.verdict,
                baseline_stability_ci_low=b.stability_ci_low,
                candidate_stability_ci_low=c.stability_ci_low,
                transition_kind=kind,
            )
        )
        if kind is TransitionKind.REGRESSED:
            regressed += 1
        elif kind is TransitionKind.IMPROVED:
            improved += 1
        elif kind is TransitionKind.UNCHANGED:
            unchanged += 1
        else:
            other_change += 1

    return DiffReport(
        baseline_session_id=baseline.session_id,
        candidate_session_id=candidate.session_id,
        materialized_hash_mismatch=baseline.materialized_hash != candidate.materialized_hash,
        transitions=transitions,
        regressed_count=regressed,
        improved_count=improved,
        unchanged_count=unchanged,
        other_change_count=other_change,
        added_count=added,
        removed_count=removed,
    )


# ---------------------------------------------------------------------------
# CLI orchestration
# ---------------------------------------------------------------------------


def _load_artifact(store: ReplayStore, session_id: str, *, role: str) -> ReplayArtifact:
    """Load an artifact, converting SessionNotFoundError to a user-facing CLIError."""
    try:
        return store.load_session(session_id)
    except SessionNotFoundError as exc:
        raise InfrastructureError(f"{role} session not found: {session_id}") from exc


def _diff_exit_code(
    report: DiffReport,
    candidate: ReplayArtifact,
    *,
    strict: bool = False,
) -> int:
    """Compute the diff exit code from a report and candidate artifact.

    Priority order (plan decision E1):
      5 (REGRESSION)         — any verdict-class downgrade, OR under --strict any
                               same-verdict confidence drop >= STRICT_CONFIDENCE_DROP_THRESHOLD
      6 (LOW_FALSIFIABILITY) — under --strict, candidate falsifiability below threshold
                               (only fires when no exit-5 trigger is present)
      0 (SUCCESS)            — no triggers
    """
    if report.regressed_count > 0:
        return 5

    if strict:
        for t in report.transitions:
            if (
                t.transition_kind is TransitionKind.UNCHANGED
                and round(t.baseline_stability_ci_low - t.candidate_stability_ci_low, 9)
                >= STRICT_CONFIDENCE_DROP_THRESHOLD
            ):
                return 5

        if candidate.session_verdict.falsifyai_falsifiability_score < LOW_FALSIFIABILITY_THRESHOLD:
            return 6

    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    """Entry point for the ``diff`` subcommand. Returns an exit code."""
    strict: bool = getattr(args, "strict", False)
    show_timeline: bool = getattr(args, "show_timeline", False)

    store = build_store(args.store_path)
    try:
        baseline = _load_artifact(store, args.baseline_session_id, role="baseline")
        candidate = _load_artifact(store, args.candidate_session_id, role="candidate")
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()

    report = compute_diff(baseline, candidate)
    render.render_diff(report, store_path=args.store_path, show_timeline=show_timeline)
    return _diff_exit_code(report, candidate, strict=strict)


__all__ = [
    "STRICT_CONFIDENCE_DROP_THRESHOLD",
    "LOW_FALSIFIABILITY_THRESHOLD",
    "CaseTransition",
    "DiffReport",
    "TransitionKind",
    "cmd_diff",
    "compute_diff",
]
