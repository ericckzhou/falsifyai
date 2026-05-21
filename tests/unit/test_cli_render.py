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
