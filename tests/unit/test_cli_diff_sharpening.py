"""RED-phase tests for PR-28 diff-sharpening: --strict, --show-timeline, exit 6.

All tests in this file import ``STRICT_CONFIDENCE_DROP_THRESHOLD`` and
``LOW_FALSIFIABILITY_THRESHOLD`` from ``falsifyai.cli.diff``.  Those constants
do not exist yet, so the entire module fails to collect in RED phase.  Once
GREEN adds the constants and the flag logic, every test here should pass.

Tests that already document a true property (introspection, exit-code parity
with no flags) will pass immediately after import is unblocked.

Covers acceptance criteria §5 of dev_notes/plans/PR-28-diff-sharpening.md:
  - Named constants present with correct values
  - --strict: confidence-drop exit 5
  - --strict: falsifiability gate exit 6
  - Exit-code priority: 5 beats 6
  - --show-timeline: all rows visible, markers, numeric delta, exit-code parity
  - Composition: --strict --show-timeline
  - Architectural assertion: diff.py must NOT import verdict.resolver
"""

import argparse
from dataclasses import replace as _replace

import pytest

from falsifyai.cli import diff as diff_module
from falsifyai.cli.diff import (
    LOW_FALSIFIABILITY_THRESHOLD,  # RED: ImportError until GREEN adds this
    STRICT_CONFIDENCE_DROP_THRESHOLD,  # RED: ImportError until GREEN adds this
)
from falsifyai.replay.in_memory_store import InMemoryStore
from falsifyai.replay.models import CaseResult, ReplayArtifact, SessionVerdict
from falsifyai.verdict.models import Verdict
from tests.fixtures.build_artifact import make_artifact

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patched_store(monkeypatch, store):
    monkeypatch.setattr(diff_module, "_build_store", lambda _path: store)
    return store


def _args(
    baseline_id: str = "b",
    candidate_id: str = "c",
    store_path: str = ":memory:",
    *,
    strict: bool = False,
    show_timeline: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        baseline_session_id=baseline_id,
        candidate_session_id=candidate_id,
        store_path=store_path,
        strict=strict,
        show_timeline=show_timeline,
    )


def _artifact_with_case_confidence(
    session_id: str,
    cases: dict[str, tuple[Verdict, float]],
    *,
    falsifiability: float = 0.65,
) -> ReplayArtifact:
    """Build a ReplayArtifact with explicit (verdict, confidence) per case.

    ``confidence`` maps to ``stability_ci_low`` — the honest confidence figure
    used in rendering and in the strict-mode confidence-drop check.
    ``falsifiability`` sets the session-level ``falsifyai_falsifiability_score``.
    """
    base = make_artifact(session_id=session_id, verdict=Verdict.STABLE)
    template = base.case_results[0]

    new_cases = []
    for case_id, (verdict, confidence) in cases.items():
        new_cases.append(
            CaseResult(
                case_id=case_id,
                original_input=template.original_input,
                original_execution=template.original_execution,
                perturbed=template.perturbed,
                verdict=verdict,
                verdict_confidence=confidence,
                stability=confidence,
                stability_ci_low=confidence,
                stability_ci_high=min(confidence + 0.05, 1.0),
                per_family_stability=template.per_family_stability,
                worst_case_family=template.worst_case_family,
            )
        )

    fragile_count = sum(1 for v, _ in cases.values() if v is Verdict.FRAGILE)
    cw_count = sum(1 for v, _ in cases.values() if v is Verdict.CONSISTENTLY_WRONG)
    if cw_count:
        session_v = Verdict.CONSISTENTLY_WRONG
    elif fragile_count:
        session_v = Verdict.FRAGILE
    else:
        session_v = Verdict.STABLE

    return _replace(
        base,
        session_id=session_id,
        case_results=new_cases,
        session_verdict=SessionVerdict(
            session_verdict=session_v,
            confidence=min(c for _, c in cases.values()),
            case_count=len(new_cases),
            fragile_count=fragile_count,
            consistently_wrong_count=cw_count,
            falsifyai_falsifiability_score=falsifiability,
        ),
    )


# ---------------------------------------------------------------------------
# Named module-level constants (acceptance criterion §5)
# ---------------------------------------------------------------------------


def test_strict_confidence_drop_threshold_is_0_10() -> None:
    """STRICT_CONFIDENCE_DROP_THRESHOLD must be exactly 0.10 per plan decision B1."""
    assert pytest.approx(0.10) == STRICT_CONFIDENCE_DROP_THRESHOLD


def test_low_falsifiability_threshold_is_0_50() -> None:
    """LOW_FALSIFIABILITY_THRESHOLD must be exactly 0.50 per plan decision D1."""
    assert pytest.approx(0.50) == LOW_FALSIFIABILITY_THRESHOLD


# ---------------------------------------------------------------------------
# --strict: confidence-drop exit 5
# ---------------------------------------------------------------------------


def test_strict_exits_5_on_confidence_drop_at_threshold(monkeypatch) -> None:
    """Confidence drop exactly == 0.10 (same verdict) triggers strict exit 5."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}))
    store.save_session(_artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.80)}))
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=True))
    assert rc == 5


def test_strict_exits_5_on_confidence_drop_above_threshold(monkeypatch) -> None:
    """Confidence drop > 0.10 (same verdict) triggers strict exit 5."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 1.00)}))
    store.save_session(_artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.50)}))
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=True))
    assert rc == 5


def test_strict_no_trigger_confidence_drop_below_threshold(monkeypatch) -> None:
    """Confidence drop < 0.10 (same verdict) does NOT trigger strict exit 5."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}))
    store.save_session(
        _artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.82)})
    )  # drop = 0.08 < 0.10
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=True))
    assert rc == 0


def test_strict_no_trigger_zero_confidence_drop(monkeypatch) -> None:
    """Identical confidence does not trigger strict exit 5."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}))
    store.save_session(_artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.90)}))
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=True))
    assert rc == 0


def test_strict_no_trigger_confidence_improved(monkeypatch) -> None:
    """Confidence increase with same verdict does NOT trigger strict exit 5."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.70)}))
    store.save_session(_artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.90)}))
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=True))
    assert rc == 0


def test_strict_verdict_class_regression_still_exits_5(monkeypatch) -> None:
    """A verdict-class regression exits 5 regardless of the --strict flag."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.95)}))
    store.save_session(_artifact_with_case_confidence("c", {"c1": (Verdict.FRAGILE, 0.45)}))
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=True))
    assert rc == 5


def test_strict_multiple_cases_one_drops_exits_5(monkeypatch) -> None:
    """One case drops >= 0.10 while others are stable → strict exit 5."""
    store = InMemoryStore()
    store.save_session(
        _artifact_with_case_confidence(
            "b", {"c1": (Verdict.STABLE, 0.90), "c2": (Verdict.STABLE, 0.90)}
        )
    )
    store.save_session(
        _artifact_with_case_confidence(
            "c", {"c1": (Verdict.STABLE, 0.90), "c2": (Verdict.STABLE, 0.70)}
        )
    )  # c2 drops 0.20
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=True))
    assert rc == 5


def test_strict_fragile_same_verdict_confidence_drop_exits_5(monkeypatch) -> None:
    """FRAGILE → FRAGILE with confidence drop >= 0.10 triggers strict exit 5."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.FRAGILE, 0.60)}))
    store.save_session(_artifact_with_case_confidence("c", {"c1": (Verdict.FRAGILE, 0.45)}))
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=True))
    assert rc == 5


def test_no_strict_flag_confidence_drop_does_not_exit_5(monkeypatch) -> None:
    """Without --strict, a large same-verdict confidence drop does NOT exit 5."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}))
    store.save_session(
        _artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.50)})
    )  # drop = 0.40 — would trigger --strict but flag is off
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=False))
    assert rc == 0


# ---------------------------------------------------------------------------
# --strict: falsifiability gate (exit 6)
# ---------------------------------------------------------------------------


def test_strict_exits_6_on_low_candidate_falsifiability(monkeypatch) -> None:
    """Candidate falsifiability < 0.50 under --strict triggers exit 6."""
    store = InMemoryStore()
    store.save_session(
        _artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}, falsifiability=0.65)
    )
    store.save_session(
        _artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.90)}, falsifiability=0.40)
    )  # no confidence drop, no verdict change; low falsifiability triggers exit 6
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=True))
    assert rc == 6


def test_strict_no_exit_6_when_falsifiability_exactly_at_threshold(monkeypatch) -> None:
    """Candidate falsifiability exactly == 0.50 does NOT trigger exit 6 (criterion is strictly <).

    Boundary: < 0.50 fires, == 0.50 does not.
    """
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}))
    store.save_session(
        _artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.90)}, falsifiability=0.50)
    )
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=True))
    assert rc == 0


def test_strict_no_exit_6_when_falsifiability_above_threshold(monkeypatch) -> None:
    """Candidate falsifiability >= 0.50 does not trigger exit 6."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}))
    store.save_session(
        _artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.90)}, falsifiability=0.70)
    )
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=True))
    assert rc == 0


def test_no_strict_flag_low_falsifiability_does_not_exit_6(monkeypatch) -> None:
    """Without --strict, low candidate falsifiability does NOT trigger exit 6."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}))
    store.save_session(
        _artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.90)}, falsifiability=0.10)
    )
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=False))
    assert rc == 0


# ---------------------------------------------------------------------------
# Exit-code priority: 5 beats 6 (plan decision E1)
# ---------------------------------------------------------------------------


def test_strict_exit_5_wins_when_both_confidence_drop_and_low_falsifiability(
    monkeypatch,
) -> None:
    """When both strict triggers fire (confidence drop + low falsifiability), exit 5 wins."""
    store = InMemoryStore()
    store.save_session(
        _artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}, falsifiability=0.65)
    )
    store.save_session(
        _artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.70)}, falsifiability=0.30)
    )  # drop=0.20 → exit 5 trigger; falsifiability=0.30 → exit 6 trigger; 5 wins
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=True))
    assert rc == 5


def test_strict_verdict_class_regression_beats_low_falsifiability(monkeypatch) -> None:
    """Verdict-class regression (exit 5) beats low falsifiability (exit 6)."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}))
    store.save_session(
        _artifact_with_case_confidence("c", {"c1": (Verdict.FRAGILE, 0.45)}, falsifiability=0.20)
    )
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=True))
    assert rc == 5


def test_strict_no_triggers_exits_0(monkeypatch) -> None:
    """--strict with healthy confidence and falsifiability exits 0."""
    store = InMemoryStore()
    store.save_session(
        _artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}, falsifiability=0.65)
    )
    store.save_session(
        _artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.88)}, falsifiability=0.70)
    )  # drop = 0.02 < 0.10; falsifiability healthy
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=True))
    assert rc == 0


# ---------------------------------------------------------------------------
# --show-timeline: all rows visible
# ---------------------------------------------------------------------------


def test_show_timeline_displays_unchanged_cases(monkeypatch, capsys) -> None:
    """--show-timeline shows every case, including unchanged rows."""
    store = InMemoryStore()
    store.save_session(
        _artifact_with_case_confidence(
            "b", {"c1": (Verdict.STABLE, 0.90), "c2": (Verdict.STABLE, 0.90)}
        )
    )
    store.save_session(
        _artifact_with_case_confidence(
            "c", {"c1": (Verdict.FRAGILE, 0.45), "c2": (Verdict.STABLE, 0.90)}
        )
    )
    _patched_store(monkeypatch, store)

    diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", show_timeline=True))
    out = capsys.readouterr().out

    assert "c1" in out  # changed case visible
    assert "c2" in out  # unchanged case also visible


def test_show_timeline_displays_added_and_removed_cases(monkeypatch, capsys) -> None:
    """--show-timeline shows ADDED and REMOVED cases in the full per-case picture."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c_old": (Verdict.STABLE, 0.90)}))
    store.save_session(_artifact_with_case_confidence("c", {"c_new": (Verdict.STABLE, 0.90)}))
    _patched_store(monkeypatch, store)

    diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", show_timeline=True))
    out = capsys.readouterr().out

    assert "c_old" in out
    assert "c_new" in out


def test_without_show_timeline_unchanged_rows_are_hidden(monkeypatch, capsys) -> None:
    """Default behavior (no --show-timeline): unchanged rows do NOT appear in output."""
    store = InMemoryStore()
    store.save_session(
        _artifact_with_case_confidence(
            "b", {"c1_changed": (Verdict.STABLE, 0.90), "c2_same": (Verdict.STABLE, 0.90)}
        )
    )
    store.save_session(
        _artifact_with_case_confidence(
            "c", {"c1_changed": (Verdict.FRAGILE, 0.45), "c2_same": (Verdict.STABLE, 0.90)}
        )
    )
    _patched_store(monkeypatch, store)

    diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c"))
    out = capsys.readouterr().out

    assert "c2_same" not in out  # unchanged row suppressed in default view


# ---------------------------------------------------------------------------
# --show-timeline: per-row markers
# ---------------------------------------------------------------------------


def test_show_timeline_regressed_marker(monkeypatch, capsys) -> None:
    """REGRESSED marker shown for verdict-class downgrade."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}))
    store.save_session(_artifact_with_case_confidence("c", {"c1": (Verdict.FRAGILE, 0.45)}))
    _patched_store(monkeypatch, store)

    diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", show_timeline=True))
    assert "REGRESSED" in capsys.readouterr().out


def test_show_timeline_improved_marker(monkeypatch, capsys) -> None:
    """IMPROVED marker shown for verdict-class upgrade."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.FRAGILE, 0.45)}))
    store.save_session(_artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.90)}))
    _patched_store(monkeypatch, store)

    diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", show_timeline=True))
    assert "IMPROVED" in capsys.readouterr().out


def test_show_timeline_declined_marker(monkeypatch, capsys) -> None:
    """DECLINED marker shown when same verdict but confidence dropped."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}))
    store.save_session(_artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.60)}))
    _patched_store(monkeypatch, store)

    diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", show_timeline=True))
    assert "DECLINED" in capsys.readouterr().out


def test_show_timeline_recovered_marker(monkeypatch, capsys) -> None:
    """RECOVERED marker shown when same verdict but confidence rose."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.FRAGILE, 0.40)}))
    store.save_session(_artifact_with_case_confidence("c", {"c1": (Verdict.FRAGILE, 0.60)}))
    _patched_store(monkeypatch, store)

    diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", show_timeline=True))
    assert "RECOVERED" in capsys.readouterr().out


def test_show_timeline_stable_marker_within_noise_floor(monkeypatch, capsys) -> None:
    """Unchanged case within 0.01 confidence noise floor is visible but not DECLINED/RECOVERED."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.900)}))
    store.save_session(
        _artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.905)})
    )  # delta = 0.005 < 0.01 noise floor
    _patched_store(monkeypatch, store)

    diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", show_timeline=True))
    out = capsys.readouterr().out

    assert "c1" in out  # case is visible
    assert "DECLINED" not in out  # not a meaningful drop
    assert "RECOVERED" not in out  # not a meaningful rise


# ---------------------------------------------------------------------------
# --show-timeline: numeric confidence delta
# ---------------------------------------------------------------------------


def test_show_timeline_includes_numeric_delta_on_declined(monkeypatch, capsys) -> None:
    """DECLINED row includes the signed numeric confidence delta."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}))
    store.save_session(_artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.60)}))
    _patched_store(monkeypatch, store)

    diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", show_timeline=True))
    out = capsys.readouterr().out

    assert "DECLINED" in out
    assert "-0.30" in out


def test_show_timeline_includes_numeric_delta_on_recovered(monkeypatch, capsys) -> None:
    """RECOVERED row includes the positive signed numeric confidence delta."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.FRAGILE, 0.50)}))
    store.save_session(_artifact_with_case_confidence("c", {"c1": (Verdict.FRAGILE, 0.70)}))
    _patched_store(monkeypatch, store)

    diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", show_timeline=True))
    out = capsys.readouterr().out

    assert "RECOVERED" in out
    assert "+0.20" in out


# ---------------------------------------------------------------------------
# --show-timeline: exit-code parity (display-only)
# ---------------------------------------------------------------------------


def test_show_timeline_does_not_change_exit_code_regression(monkeypatch) -> None:
    """--show-timeline is display-only; a regression still exits 5."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}))
    store.save_session(_artifact_with_case_confidence("c", {"c1": (Verdict.FRAGILE, 0.45)}))
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", show_timeline=True))
    assert rc == 5


def test_show_timeline_does_not_change_exit_code_no_regression(monkeypatch) -> None:
    """--show-timeline is display-only; no regression still exits 0."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}))
    store.save_session(_artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.85)}))
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", show_timeline=True))
    assert rc == 0


# ---------------------------------------------------------------------------
# Composition: --strict --show-timeline
# ---------------------------------------------------------------------------


def test_strict_and_show_timeline_all_rows_visible(monkeypatch, capsys) -> None:
    """--strict --show-timeline: every case row is rendered, including unchanged."""
    store = InMemoryStore()
    store.save_session(
        _artifact_with_case_confidence(
            "b", {"c1": (Verdict.STABLE, 0.90), "c2": (Verdict.STABLE, 0.90)}
        )
    )
    store.save_session(
        _artifact_with_case_confidence(
            "c", {"c1": (Verdict.STABLE, 0.70), "c2": (Verdict.STABLE, 0.90)}
        )
    )  # c1 drops 0.20 → strict; c2 unchanged → visible only with --show-timeline
    _patched_store(monkeypatch, store)

    diff_module.cmd_diff(_args(baseline_id="b", candidate_id="c", strict=True, show_timeline=True))
    out = capsys.readouterr().out

    assert "c1" in out  # declined case visible
    assert "c2" in out  # unchanged case visible due to --show-timeline


def test_strict_and_show_timeline_strict_exit_code(monkeypatch) -> None:
    """--strict --show-timeline: exit code is the strict-mode result (5 for confidence drop)."""
    store = InMemoryStore()
    store.save_session(_artifact_with_case_confidence("b", {"c1": (Verdict.STABLE, 0.90)}))
    store.save_session(_artifact_with_case_confidence("c", {"c1": (Verdict.STABLE, 0.70)}))
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(
        _args(baseline_id="b", candidate_id="c", strict=True, show_timeline=True)
    )
    assert rc == 5


def test_strict_and_show_timeline_exit_6_with_full_row_list(monkeypatch, capsys) -> None:
    """--strict --show-timeline: exit 6 (low falsifiability) + all cases rendered."""
    store = InMemoryStore()
    store.save_session(
        _artifact_with_case_confidence(
            "b",
            {"c1": (Verdict.STABLE, 0.90), "c2": (Verdict.STABLE, 0.90)},
            falsifiability=0.65,
        )
    )
    store.save_session(
        _artifact_with_case_confidence(
            "c",
            {"c1": (Verdict.STABLE, 0.88), "c2": (Verdict.STABLE, 0.88)},
            falsifiability=0.30,  # < 0.50 → exit 6; no confidence drop >= 0.10
        )
    )
    _patched_store(monkeypatch, store)

    rc = diff_module.cmd_diff(
        _args(baseline_id="b", candidate_id="c", strict=True, show_timeline=True)
    )
    out = capsys.readouterr().out

    assert rc == 6
    assert "c1" in out
    assert "c2" in out


# ---------------------------------------------------------------------------
# Architectural assertion: diff.py must NOT import verdict.resolver
# ---------------------------------------------------------------------------


def test_diff_does_not_import_resolver() -> None:
    """falsifyai.cli.diff must not transitively import falsifyai.verdict.resolver.

    Enforces the consumer-surface separation in §11 of PR-28 plan: diff is a
    pure reader of preserved artifacts.  Re-resolving on read violates the
    no-re-resolution invariant and the architectural rule from CLAUDE.md.
    """
    import sys

    for mod_name in list(sys.modules):
        if mod_name.startswith("falsifyai.cli.diff"):
            del sys.modules[mod_name]
        if mod_name == "falsifyai.verdict.resolver":
            del sys.modules[mod_name]

    import falsifyai.cli.diff  # noqa: F401

    assert "falsifyai.verdict.resolver" not in sys.modules, (
        "falsifyai.cli.diff must not import falsifyai.verdict.resolver "
        "(re-resolving violates the preservation guarantee). "
        "Read case.verdict from the loaded artifact instead."
    )
