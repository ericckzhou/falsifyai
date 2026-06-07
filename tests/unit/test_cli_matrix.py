"""Tests for falsifyai.cli.matrix (reliability matrix)."""

import argparse
import io
from types import SimpleNamespace

import falsifyai.cli.matrix as matrix_mod
from falsifyai.cli.matrix import _render, _worst_per_family, compute_matrix


def _case(per_family: dict[str, float]):
    return SimpleNamespace(per_family_stability=per_family)


def _artifact(session_id: str, model: str, verdict: str, cases: list):
    provider, _, name = model.partition(":")
    return SimpleNamespace(
        session_id=session_id,
        materialized=SimpleNamespace(model=SimpleNamespace(provider=provider, model=name)),
        session_verdict=SimpleNamespace(session_verdict=SimpleNamespace(value=verdict)),
        case_results=cases,
    )


def test_worst_per_family_takes_minimum_across_cases() -> None:
    artifact = _artifact(
        "s1",
        "openai:gpt-4o",
        "fragile",
        [_case({"typo_noise": 0.9, "casing": 1.0}), _case({"typo_noise": 0.4})],
    )
    worst = _worst_per_family(artifact)
    assert worst == {"typo_noise": 0.4, "casing": 1.0}  # min for typo_noise


def test_compute_matrix_shape_and_cells() -> None:
    a = _artifact(
        "sessionAAA", "openai:gpt-4o", "stable", [_case({"typo_noise": 0.95, "unicode": 0.3})]
    )
    b = _artifact("sessionBBB", "anthropic:claude", "fragile", [_case({"typo_noise": 0.4})])
    report = compute_matrix([a, b])

    assert report.families == ["typo_noise", "unicode"]  # sorted union
    assert [c.label for c in report.columns] == ["M1", "M2"]
    assert report.cells[("typo_noise", "sessionAAA")] == 0.95
    assert report.cells[("typo_noise", "sessionBBB")] == 0.4
    # unicode absent in session B -> blank cell
    assert report.cells[("unicode", "sessionBBB")] is None


def test_render_contains_rows_and_legend() -> None:
    a = _artifact("sessionAAA", "openai:gpt-4o", "stable", [_case({"unicode": 0.3})])
    b = _artifact("sessionBBB", "anthropic:claude", "fragile", [_case({"unicode": 0.2})])
    report = compute_matrix([a, b])
    buf = io.StringIO()
    _render(report, stream=buf)
    out = buf.getvalue()
    assert "unicode" in out
    assert "M1" in out and "M2" in out
    assert "0.30" in out and "0.20" in out
    assert "openai:gpt-4o" in out  # legend
    assert "anthropic:claude" in out


def test_cmd_matrix_unknown_session_raises(tmp_path) -> None:
    from falsifyai.cli.errors import InfrastructureError

    args = argparse.Namespace(session_ids=["nope"], store_path=str(tmp_path / "empty.db"))
    try:
        matrix_mod.cmd_matrix(args)
    except InfrastructureError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("expected InfrastructureError")
