"""Tests for falsifyai.cli.diff — differential testing across two stored sessions.

The diff command is the launch wedge per [plan.md §22.1](../../plan.md):
compares two ReplayArtifacts, surfaces verdict transitions, and returns
exit code 5 (REGRESSION) if any case regressed.

Discipline check: zero resolver changes. Diff is a pure consumer of
already-resolved artifacts.
"""

import argparse

import pytest

from falsifyai.cli import diff as diff_module
from falsifyai.cli.diff import (
    TransitionKind,
    _classify_transition,
    compute_diff,
)
from falsifyai.cli.errors import CLIError
from falsifyai.replay.in_memory_store import InMemoryStore
from falsifyai.replay.models import CaseResult, ReplayArtifact, SessionVerdict
from falsifyai.verdict.models import Verdict
from tests.fixtures.build_artifact import make_artifact


def _patched_store(monkeypatch, store):
    monkeypatch.setattr(diff_module, "build_store", lambda _path: store)
    return store


def _args(baseline_id="b", candidate_id="c", store_path=":memory:"):
    return argparse.Namespace(
        baseline_session_id=baseline_id,
        candidate_session_id=candidate_id,
        store_path=store_path,
    )


def _artifact_with_case_verdicts(session_id: str, case_verdicts: dict[str, Verdict]):
    """Build a ReplayArtifact that has the given (case_id -> verdict) mapping.

    Stability point estimates: STABLE=0.95, FRAGILE=0.45, CONSISTENTLY_WRONG=0.1,
    INSUFFICIENT=0.0, INVALID_EVAL=0.0. CI bounds match the point estimate
    for simplicity (tests don't care about width here).
    """
    base = make_artifact(session_id=session_id, verdict=Verdict.STABLE)
    point_map = {
        Verdict.STABLE: 0.95,
        Verdict.FRAGILE: 0.45,
        Verdict.CONSISTENTLY_WRONG: 0.10,
        Verdict.INSUFFICIENT: 0.0,
        Verdict.INVALID_EVAL: 0.0,
    }
    new_cases = []
    for case_id, verdict in case_verdicts.items():
        stability = point_map[verdict]
        # Reuse the template case but override case_id, verdict, stability.
        template = base.case_results[0]
        new_cases.append(
            CaseResult(
                case_id=case_id,
                original_input=template.original_input,
                original_execution=template.original_execution,
                perturbed=template.perturbed,
                verdict=verdict,
                verdict_confidence=stability,
                stability=stability,
                stability_ci_low=stability,
                stability_ci_high=stability,
                per_family_stability=template.per_family_stability,
                worst_case_family=template.worst_case_family,
            )
        )
    # Session verdict roll-up (rough; tests don't check counts here).
    fragile_count = sum(1 for v in case_verdicts.values() if v is Verdict.FRAGILE)
    cw_count = sum(1 for v in case_verdicts.values() if v is Verdict.CONSISTENTLY_WRONG)
    if cw_count:
        session_v = Verdict.CONSISTENTLY_WRONG
    elif fragile_count:
        session_v = Verdict.FRAGILE
    else:
        session_v = Verdict.STABLE
    return ReplayArtifact(
        session_id=session_id,
        created_at=base.created_at,
        falsifyai_version=base.falsifyai_version,
        spec_hash=base.spec_hash,
        materialized_hash=base.materialized_hash,
        materialized=base.materialized,
        case_results=new_cases,
        session_verdict=SessionVerdict(
            session_verdict=session_v,
            confidence=0.5,
            case_count=len(new_cases),
            fragile_count=fragile_count,
            consistently_wrong_count=cw_count,
        ),
    )


# ---------------------------------------------------------------------------
# _classify_transition
# ---------------------------------------------------------------------------


def test_classify_same_verdict_is_unchanged() -> None:
    assert _classify_transition(Verdict.STABLE, Verdict.STABLE) is TransitionKind.UNCHANGED
    assert _classify_transition(Verdict.FRAGILE, Verdict.FRAGILE) is TransitionKind.UNCHANGED


def test_classify_stable_to_fragile_is_regressed() -> None:
    assert _classify_transition(Verdict.STABLE, Verdict.FRAGILE) is TransitionKind.REGRESSED


def test_classify_stable_to_consistently_wrong_is_regressed() -> None:
    assert (
        _classify_transition(Verdict.STABLE, Verdict.CONSISTENTLY_WRONG) is TransitionKind.REGRESSED
    )


def test_classify_fragile_to_consistently_wrong_is_regressed() -> None:
    assert (
        _classify_transition(Verdict.FRAGILE, Verdict.CONSISTENTLY_WRONG)
        is TransitionKind.REGRESSED
    )


def test_classify_fragile_to_stable_is_improved() -> None:
    assert _classify_transition(Verdict.FRAGILE, Verdict.STABLE) is TransitionKind.IMPROVED


def test_classify_consistently_wrong_to_stable_is_improved() -> None:
    assert (
        _classify_transition(Verdict.CONSISTENTLY_WRONG, Verdict.STABLE) is TransitionKind.IMPROVED
    )


def test_classify_insufficient_to_stable_is_improved() -> None:
    """Going from 'no evidence' to STABLE is unambiguously better."""
    assert _classify_transition(Verdict.INSUFFICIENT, Verdict.STABLE) is TransitionKind.IMPROVED


def test_classify_stable_to_insufficient_is_other_change() -> None:
    """Losing evidence isn't a regression in the verdict-class sense, but it's
    informational. Not REGRESSED, not IMPROVED, not UNCHANGED."""
    kind = _classify_transition(Verdict.STABLE, Verdict.INSUFFICIENT)
    assert kind is TransitionKind.OTHER_CHANGE


# --- verdict quality ladder (PR-K) -------------------------------------------


def test_classify_information_present_to_stable_is_regressed() -> None:
    """Losing confirmed grounding is a downgrade."""
    assert (
        _classify_transition(Verdict.INFORMATION_PRESENT, Verdict.STABLE)
        is TransitionKind.REGRESSED
    )


def test_classify_stable_to_ambiguous_is_regressed() -> None:
    assert _classify_transition(Verdict.STABLE, Verdict.AMBIGUOUS) is TransitionKind.REGRESSED


def test_classify_fragile_to_adversarially_vulnerable_is_regressed() -> None:
    assert (
        _classify_transition(Verdict.FRAGILE, Verdict.ADVERSARIALLY_VULNERABLE)
        is TransitionKind.REGRESSED
    )


def test_classify_adversarially_vulnerable_to_stable_is_improved() -> None:
    assert (
        _classify_transition(Verdict.ADVERSARIALLY_VULNERABLE, Verdict.STABLE)
        is TransitionKind.IMPROVED
    )


def test_classify_same_tier_is_other_change() -> None:
    """AMBIGUOUS and INFORMATION_NULL are the same severity tier -> no clear up/down."""
    assert (
        _classify_transition(Verdict.AMBIGUOUS, Verdict.INFORMATION_NULL)
        is TransitionKind.OTHER_CHANGE
    )


def test_classify_invalid_eval_transitions_are_other_change() -> None:
    """INVALID_EVAL is off the quality ladder -> never a regression/improvement."""
    assert _classify_transition(Verdict.STABLE, Verdict.INVALID_EVAL) is TransitionKind.OTHER_CHANGE
    assert _classify_transition(Verdict.INVALID_EVAL, Verdict.STABLE) is TransitionKind.OTHER_CHANGE


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


def test_compute_diff_identical_artifacts_no_changes() -> None:
    a = _artifact_with_case_verdicts("a", {"c1": Verdict.STABLE, "c2": Verdict.STABLE})
    b = _artifact_with_case_verdicts("b", {"c1": Verdict.STABLE, "c2": Verdict.STABLE})
    report = compute_diff(a, b)
    assert report.regressed_count == 0
    assert report.improved_count == 0
    assert report.unchanged_count == 2
    assert report.added_count == 0
    assert report.removed_count == 0


def test_compute_diff_single_regression() -> None:
    base = _artifact_with_case_verdicts("a", {"c1": Verdict.STABLE, "c2": Verdict.STABLE})
    cand = _artifact_with_case_verdicts("b", {"c1": Verdict.STABLE, "c2": Verdict.FRAGILE})
    report = compute_diff(base, cand)
    assert report.regressed_count == 1
    assert report.unchanged_count == 1
    # The regressed transition is for c2 with the expected verdicts.
    regressed = [t for t in report.transitions if t.transition_kind is TransitionKind.REGRESSED]
    assert len(regressed) == 1
    assert regressed[0].case_id == "c2"
    assert regressed[0].baseline_verdict is Verdict.STABLE
    assert regressed[0].candidate_verdict is Verdict.FRAGILE


def test_compute_diff_case_added_in_candidate() -> None:
    base = _artifact_with_case_verdicts("a", {"c1": Verdict.STABLE})
    cand = _artifact_with_case_verdicts("b", {"c1": Verdict.STABLE, "c2_new": Verdict.STABLE})
    report = compute_diff(base, cand)
    assert report.added_count == 1
    assert report.removed_count == 0
    assert report.regressed_count == 0
    added = [t for t in report.transitions if t.transition_kind is TransitionKind.ADDED]
    assert added[0].case_id == "c2_new"
    assert added[0].baseline_verdict is None
    assert added[0].candidate_verdict is Verdict.STABLE


def test_compute_diff_case_removed_in_candidate() -> None:
    base = _artifact_with_case_verdicts("a", {"c1": Verdict.STABLE, "c2_gone": Verdict.STABLE})
    cand = _artifact_with_case_verdicts("b", {"c1": Verdict.STABLE})
    report = compute_diff(base, cand)
    assert report.removed_count == 1
    assert report.regressed_count == 0
    removed = [t for t in report.transitions if t.transition_kind is TransitionKind.REMOVED]
    assert removed[0].case_id == "c2_gone"


def test_compute_diff_detects_materialized_hash_mismatch() -> None:
    base = _artifact_with_case_verdicts("a", {"c1": Verdict.STABLE})
    cand = _artifact_with_case_verdicts("b", {"c1": Verdict.STABLE})
    # Manually craft a candidate with a different materialized_hash.
    from dataclasses import replace as _replace

    cand_different_hash = _replace(cand, materialized_hash="z" * 64)
    report = compute_diff(base, cand_different_hash)
    assert report.materialized_hash_mismatch is True


def test_compute_diff_matching_materialized_hash() -> None:
    base = _artifact_with_case_verdicts("a", {"c1": Verdict.STABLE})
    cand = _artifact_with_case_verdicts("b", {"c1": Verdict.STABLE})
    # Same fixture template -> same materialized_hash.
    report = compute_diff(base, cand)
    assert report.materialized_hash_mismatch is False


# ---------------------------------------------------------------------------
# cmd_diff
# ---------------------------------------------------------------------------


def test_cmd_diff_no_regression_returns_zero(monkeypatch, capsys) -> None:
    store = InMemoryStore()
    store.save_session(_artifact_with_case_verdicts("b1", {"c1": Verdict.STABLE}))
    store.save_session(_artifact_with_case_verdicts("c1", {"c1": Verdict.STABLE}))
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b1", candidate_id="c1"))
    assert rc == 0


def test_cmd_diff_regression_returns_exit_code_five(monkeypatch, capsys) -> None:
    store = InMemoryStore()
    store.save_session(_artifact_with_case_verdicts("b1", {"c1": Verdict.STABLE}))
    store.save_session(_artifact_with_case_verdicts("c1", {"c1": Verdict.FRAGILE}))
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b1", candidate_id="c1"))
    assert rc == 5


def test_cmd_diff_missing_baseline_raises_cli_error(monkeypatch) -> None:
    store = InMemoryStore()
    store.save_session(_artifact_with_case_verdicts("only-candidate", {"c1": Verdict.STABLE}))
    _patched_store(monkeypatch, store)

    with pytest.raises(CLIError) as exc_info:
        diff_module.cmd_diff(_args(baseline_id="missing", candidate_id="only-candidate"))
    assert exc_info.value.exit_code == 3
    assert "missing" in str(exc_info.value)


def test_cmd_diff_missing_candidate_raises_cli_error(monkeypatch) -> None:
    store = InMemoryStore()
    store.save_session(_artifact_with_case_verdicts("only-baseline", {"c1": Verdict.STABLE}))
    _patched_store(monkeypatch, store)

    with pytest.raises(CLIError) as exc_info:
        diff_module.cmd_diff(_args(baseline_id="only-baseline", candidate_id="missing"))
    assert exc_info.value.exit_code == 3
    assert "missing" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Read-only invariant
# ---------------------------------------------------------------------------


def test_cmd_diff_does_not_modify_either_artifact(monkeypatch) -> None:
    store = InMemoryStore()
    b_orig = _artifact_with_case_verdicts("readonly-b", {"c1": Verdict.STABLE})
    c_orig = _artifact_with_case_verdicts("readonly-c", {"c1": Verdict.FRAGILE})
    store.save_session(b_orig)
    store.save_session(c_orig)
    _patched_store(monkeypatch, store)

    diff_module.cmd_diff(_args(baseline_id="readonly-b", candidate_id="readonly-c"))

    assert store.load_session("readonly-b") == b_orig
    assert store.load_session("readonly-c") == c_orig
