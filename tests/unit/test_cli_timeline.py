"""Tests for falsifyai.cli.timeline."""

import argparse
from types import SimpleNamespace

import falsifyai.cli.timeline as timeline_mod
from falsifyai.cli.timeline import _sparkline, compute_timeline
from falsifyai.verdict.models import Verdict


def _pair(sid: str, ci: float, verdict: Verdict):
    artifact = SimpleNamespace(
        session_id=sid,
        created_at=SimpleNamespace(isoformat=lambda: "2026-06-04T00:00:00"),
    )
    case = SimpleNamespace(stability_ci_low=ci, verdict=verdict)
    return (artifact, case)


def test_regression_flagged_on_downgrade() -> None:
    report = compute_timeline(
        [_pair("s1", 0.95, Verdict.STABLE), _pair("s2", 0.40, Verdict.FRAGILE)]
    )
    assert report.points[0].regressed_from_prev is False  # first point never regresses
    assert report.points[1].regressed_from_prev is True
    assert report.has_regression is True
    assert report.regression_count == 1


def test_no_regression_when_stable_throughout() -> None:
    report = compute_timeline(
        [_pair("s1", 0.95, Verdict.STABLE), _pair("s2", 0.97, Verdict.STABLE)]
    )
    assert report.has_regression is False


def test_improvement_is_not_a_regression() -> None:
    report = compute_timeline(
        [_pair("s1", 0.40, Verdict.FRAGILE), _pair("s2", 0.99, Verdict.STABLE)]
    )
    assert report.points[1].regressed_from_prev is False
    assert report.has_regression is False


def test_sparkline_maps_low_to_high() -> None:
    line = _sparkline([0.0, 1.0])
    assert line[0] == " "  # lowest level
    assert line[-1] == "@"  # highest level


def test_cmd_timeline_unknown_case_raises(tmp_path) -> None:
    from falsifyai.cli.errors import InfrastructureError

    args = argparse.Namespace(case_id="nope", limit=20, store_path=str(tmp_path / "empty.db"))
    try:
        timeline_mod.cmd_timeline(args)
    except InfrastructureError as exc:
        assert "no sessions found" in str(exc)
    else:
        raise AssertionError("expected InfrastructureError")
