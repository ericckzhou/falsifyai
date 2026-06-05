"""Tests for falsifyai.cli.render — plain-text terminal output."""

import io

from falsifyai.cli.render import exit_code_for, render_session
from falsifyai.verdict.models import Verdict
from tests.fixtures.build_artifact import make_artifact

# ---------------------------------------------------------------------------
# exit_code_for — maps the MVP 5 verdicts to CI codes per plan §16.1
# ---------------------------------------------------------------------------


def test_exit_code_stable_is_zero() -> None:
    assert exit_code_for(Verdict.STABLE) == 0


def test_exit_code_fragile_is_one() -> None:
    assert exit_code_for(Verdict.FRAGILE) == 1


def test_exit_code_consistently_wrong_is_two() -> None:
    assert exit_code_for(Verdict.CONSISTENTLY_WRONG) == 2


def test_exit_code_invalid_eval_is_two() -> None:
    assert exit_code_for(Verdict.INVALID_EVAL) == 2


def test_exit_code_insufficient_is_four() -> None:
    assert exit_code_for(Verdict.INSUFFICIENT) == 4


# ---------------------------------------------------------------------------
# render_session — per-case rows + summary footer
# ---------------------------------------------------------------------------


def test_render_includes_case_id_and_verdict() -> None:
    artifact = make_artifact(verdict=Verdict.STABLE)
    buf = io.StringIO()
    render_session(artifact, store_path=".falsifyai/replays.db", stream=buf)
    output = buf.getvalue()
    assert "capital_of_france" in output
    assert "STABLE" in output


def test_render_includes_session_id_and_store_path() -> None:
    artifact = make_artifact(session_id="sess-render-1")
    buf = io.StringIO()
    render_session(artifact, store_path=".falsifyai/replays.db", stream=buf)
    output = buf.getvalue()
    assert "sess-render-1" in output
    assert ".falsifyai/replays.db" in output


def test_render_includes_summary_counts() -> None:
    artifact = make_artifact(verdict=Verdict.FRAGILE)
    buf = io.StringIO()
    render_session(artifact, store_path=":memory:", stream=buf)
    output = buf.getvalue()
    # SessionVerdict for FRAGILE artifact has fragile_count=1
    assert "1 case" in output
    assert "FRAGILE" in output


def test_render_relabels_instability_band_as_stability_floor() -> None:
    """Instability-band verdicts surface ``verdict_confidence`` as a stability
    *floor*, not ``confidence``. The number is the CI lower bound -- near 0 when
    the case is most broken -- so labeling it ``confidence`` would invert its
    meaning. See docs/case-studies/05-confidence-floor-inversion.md."""
    for verdict in (
        Verdict.ADVERSARIALLY_VULNERABLE,
        Verdict.FRAGILE,
        Verdict.AMBIGUOUS,
    ):
        buf = io.StringIO()
        render_session(make_artifact(verdict=verdict), store_path=":memory:", stream=buf)
        output = buf.getvalue()
        assert "stability floor:" in output, verdict
        assert "confidence:" not in output, verdict


def test_render_keeps_confidence_label_for_stable_band() -> None:
    """Stable-band verdicts read ``verdict_confidence`` as genuine
    confidence-in-stability and keep the ``confidence`` label."""
    for verdict in (
        Verdict.STABLE,
        Verdict.INFORMATION_PRESENT,
        Verdict.INFORMATION_NULL,
    ):
        buf = io.StringIO()
        render_session(make_artifact(verdict=verdict), store_path=":memory:", stream=buf)
        output = buf.getvalue()
        assert "confidence:" in output, verdict
        assert "stability floor:" not in output, verdict


def test_render_includes_ci_bounds_per_case() -> None:
    """PR #11 evidence-density choice: CI width changes the engineer's decision."""
    artifact = make_artifact(verdict=Verdict.STABLE)
    buf = io.StringIO()
    render_session(artifact, store_path=":memory:", stream=buf)
    output = buf.getvalue()
    assert "CI:" in output


def test_render_footer_includes_falsifiability() -> None:
    artifact = make_artifact(verdict=Verdict.STABLE)
    buf = io.StringIO()
    render_session(artifact, store_path=":memory:", stream=buf)
    output = buf.getvalue()
    assert "falsifiability" in output


# ---------------------------------------------------------------------------
# PR #13: loaded_from header for replay + legacy artifact handling
# ---------------------------------------------------------------------------


def test_loaded_from_header_appears_when_set() -> None:
    """Replay path prepends a 'Loaded session' line before per-case rows."""
    from datetime import UTC, datetime

    artifact = make_artifact(session_id="sess-loaded-1", verdict=Verdict.STABLE)
    loaded_from = datetime(2026, 5, 21, 10, 0, 0, tzinfo=UTC)
    buf = io.StringIO()
    render_session(
        artifact, store_path=".falsifyai/replays.db", stream=buf, loaded_from=loaded_from
    )
    output = buf.getvalue()
    assert "Loaded session sess-loaded-1" in output
    assert "2026-05-21T10:00:00" in output


def test_loaded_from_none_keeps_run_output_unchanged() -> None:
    """Regression guard: run path (loaded_from=None) gets PR #11's exact output."""
    artifact = make_artifact(verdict=Verdict.STABLE)
    without = io.StringIO()
    explicit_none = io.StringIO()
    render_session(artifact, store_path=":memory:", stream=without)
    render_session(artifact, store_path=":memory:", stream=explicit_none, loaded_from=None)
    assert without.getvalue() == explicit_none.getvalue()


def test_legacy_case_renders_legacy_marker_instead_of_ci() -> None:
    """A CaseResult with zero CI fields + nonzero verdict_confidence is pre-PR-11
    and shouldn't display misleading (CI: 0.00-0.00)."""
    from datetime import UTC, datetime

    from falsifyai.execution.models import Execution, ModelRequest
    from falsifyai.replay.models import (
        CaseResult,
        ReplayArtifact,
        SessionVerdict,
    )
    from falsifyai.spec.materializer import MaterializedSpec
    from falsifyai.spec.models import ModelConfig, RunConfig

    req = ModelRequest(
        provider="mock",
        model="mock",
        prompt="p",
        temperature=0.0,
        max_tokens=128,
        seed=42,
        timeout_seconds=30,
    )
    exec_ = Execution(
        request=req,
        output_text="o",
        latency_ms=1.0,
        prompt_tokens=1,
        completion_tokens=1,
        cached=False,
        seed_provided=True,
    )
    legacy_case = CaseResult(
        case_id="legacy_case",
        original_input="p",
        original_execution=exec_,
        perturbed=[],
        verdict=Verdict.STABLE,
        verdict_confidence=0.83,  # nonzero -> not INSUFFICIENT, just no CI evidence
        stability=0.0,  # default; pre-PR-11 artifact
        stability_ci_low=0.0,
        stability_ci_high=0.0,
        per_family_stability={},
        worst_case_family=None,
    )
    artifact = ReplayArtifact(
        session_id="sess-legacy",
        created_at=datetime(2026, 5, 21, tzinfo=UTC),
        falsifyai_version="0.0.1",
        spec_hash="x" * 64,
        materialized_hash="y" * 64,
        materialized=MaterializedSpec(
            spec_hash="x" * 64,
            materialized_hash="y" * 64,
            session_seed=42,
            falsifyai_version="0.0.1",
            model=ModelConfig(provider="mock", model="mock"),
            run=RunConfig(seed=42),
            cases=[],
        ),
        case_results=[legacy_case],
        session_verdict=SessionVerdict(
            session_verdict=Verdict.STABLE,
            confidence=0.83,
            case_count=1,
            fragile_count=0,
            consistently_wrong_count=0,
        ),
    )
    buf = io.StringIO()
    render_session(artifact, store_path=":memory:", stream=buf)
    output = buf.getvalue()
    assert "legacy" in output.lower()
    assert "CI:" not in output  # misleading CI column suppressed


def test_non_legacy_case_still_shows_ci() -> None:
    """make_artifact() returns a PR-11-era case; it should keep the CI column."""
    artifact = make_artifact(verdict=Verdict.STABLE)
    buf = io.StringIO()
    render_session(artifact, store_path=":memory:", stream=buf)
    output = buf.getvalue()
    assert "CI:" in output
    assert "legacy" not in output.lower()


# ---------------------------------------------------------------------------
# PR #14: render_diff
# ---------------------------------------------------------------------------


def test_render_diff_no_transitions_prints_summary() -> None:
    from falsifyai.cli.diff import DiffReport
    from falsifyai.cli.render import render_diff

    report = DiffReport(
        baseline_session_id="b1",
        candidate_session_id="c1",
        materialized_hash_mismatch=False,
        transitions=[],
        regressed_count=0,
        improved_count=0,
        unchanged_count=3,
        other_change_count=0,
        added_count=0,
        removed_count=0,
    )
    buf = io.StringIO()
    render_diff(report, store_path=":memory:", stream=buf)
    output = buf.getvalue()
    assert "no transitions" in output.lower()
    assert "0 regressed" in output
    assert "3 unchanged" in output


def test_render_diff_with_regression_shows_transition_row() -> None:
    from falsifyai.cli.diff import CaseTransition, DiffReport, TransitionKind
    from falsifyai.cli.render import render_diff

    transition = CaseTransition(
        case_id="capital_of_france",
        baseline_verdict=Verdict.STABLE,
        candidate_verdict=Verdict.FRAGILE,
        baseline_stability_ci_low=0.92,
        candidate_stability_ci_low=0.45,
        transition_kind=TransitionKind.REGRESSED,
    )
    report = DiffReport(
        baseline_session_id="b1",
        candidate_session_id="c1",
        materialized_hash_mismatch=False,
        transitions=[transition],
        regressed_count=1,
        improved_count=0,
        unchanged_count=0,
        other_change_count=0,
        added_count=0,
        removed_count=0,
    )
    buf = io.StringIO()
    render_diff(report, store_path=":memory:", stream=buf)
    output = buf.getvalue()
    assert "capital_of_france" in output
    assert "STABLE" in output and "FRAGILE" in output
    assert "0.92" in output and "0.45" in output
    assert "REGRESSED" in output
    assert "1 regressed" in output


def test_render_diff_materialized_hash_mismatch_prints_warning() -> None:
    from falsifyai.cli.diff import DiffReport
    from falsifyai.cli.render import render_diff

    report = DiffReport(
        baseline_session_id="b1",
        candidate_session_id="c1",
        materialized_hash_mismatch=True,
        transitions=[],
        regressed_count=0,
        improved_count=0,
        unchanged_count=0,
        other_change_count=0,
        added_count=0,
        removed_count=0,
    )
    buf = io.StringIO()
    render_diff(report, store_path=":memory:", stream=buf)
    output = buf.getvalue()
    assert "materialized_hash differs" in output
