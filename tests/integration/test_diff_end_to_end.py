"""End-to-end integration tests for ``falsifyai diff``.

Proves the run -> save -> diff chain. Two consecutive ``cmd_run``
invocations against the same spec with different MockAdapter responses
should produce a regression detectable by ``cmd_diff``.
"""

import argparse
from pathlib import Path

import falsifyai.cli.diff as cli_diff
import falsifyai.cli.run as cli_run
from falsifyai.replay.sqlite_store import SQLiteStore
from tests.fixtures.mock_adapter import MockAdapter

_SMOKE_SPEC = Path(__file__).resolve().parents[1] / "fixtures" / "specs" / "run_smoke.yaml"


def _run_args(spec_path: Path, store_path: str) -> argparse.Namespace:
    return argparse.Namespace(spec_path=str(spec_path), store_path=store_path)


def _diff_args(baseline: str, candidate: str, store_path: str) -> argparse.Namespace:
    return argparse.Namespace(
        baseline_session_id=baseline,
        candidate_session_id=candidate,
        store_path=store_path,
    )


def _two_sessions(store_path: str, baseline_response: str, candidate_response: str):
    """Run twice with different adapter responses; return (baseline_id, candidate_id)."""
    import falsifyai.cli.run as cli_run_mod

    # Baseline run.
    baseline_adapter = MockAdapter(default_response=baseline_response)
    _orig_build = cli_run_mod.build_adapter
    cli_run_mod.build_adapter = lambda model: baseline_adapter  # type: ignore[assignment]
    try:
        cli_run.cmd_run(_run_args(_SMOKE_SPEC, store_path))
    finally:
        cli_run_mod.build_adapter = _orig_build  # type: ignore[assignment]

    # Candidate run.
    candidate_adapter = MockAdapter(default_response=candidate_response)
    cli_run_mod.build_adapter = lambda model: candidate_adapter  # type: ignore[assignment]
    try:
        cli_run.cmd_run(_run_args(_SMOKE_SPEC, store_path))
    finally:
        cli_run_mod.build_adapter = _orig_build  # type: ignore[assignment]

    # Retrieve both session ids from the store (newest-first).
    with SQLiteStore(store_path) as store:
        sessions = list(store.query_sessions(limit=2))
    assert len(sessions) == 2
    candidate_id, baseline_id = sessions[0].session_id, sessions[1].session_id
    return baseline_id, candidate_id


def test_diff_no_change_returns_zero(tmp_path, capsys) -> None:
    db_path = str(tmp_path / "replays.db")
    baseline_id, candidate_id = _two_sessions(
        db_path,
        baseline_response="Paris is the capital of France.",
        candidate_response="Paris is the capital of France.",
    )
    capsys.readouterr()  # discard run output

    rc = cli_diff.cmd_diff(_diff_args(baseline_id, candidate_id, db_path))
    assert rc == 0


def test_diff_regression_returns_exit_code_five(tmp_path, capsys) -> None:
    """Baseline gives correct answer; candidate gives wrong answer -> regression."""
    db_path = str(tmp_path / "replays.db")
    baseline_id, candidate_id = _two_sessions(
        db_path,
        baseline_response="Paris is the capital of France.",  # contains 'Paris' -> STABLE
        candidate_response="I don't know.",  # missing 'Paris' on all -> CONSISTENTLY_WRONG
    )
    capsys.readouterr()

    rc = cli_diff.cmd_diff(_diff_args(baseline_id, candidate_id, db_path))
    assert rc == 5  # REGRESSION

    captured = capsys.readouterr()
    assert "REGRESSED" in captured.out
    assert "1 regressed" in captured.out


def test_diff_via_main_cli_returns_exit_code(tmp_path, capsys) -> None:
    """End-to-end through cli/main.py argparse dispatch."""
    import falsifyai.cli.main as cli_main

    db_path = str(tmp_path / "replays.db")
    baseline_id, candidate_id = _two_sessions(
        db_path,
        baseline_response="Paris is the capital of France.",
        candidate_response="I don't know.",
    )
    capsys.readouterr()

    rc = cli_main.main(["diff", baseline_id, candidate_id, "--store-path", db_path])
    assert rc == 5


# ---------------------------------------------------------------------------
# Byte-identical backward-compatibility fixture (acceptance criterion J1)
# ---------------------------------------------------------------------------


def test_diff_default_output_is_byte_identical_to_v020_baseline(capsys) -> None:
    """Default ``falsifyai diff`` output must be byte-identical to the v0.2.0 fixture.

    This is the mechanical guard for plan decision J1 (backward compatibility).
    The fixture at tests/fixtures/diff/v0.2.0_baseline.txt was captured against
    the case-study replay DB on the v0.2.0 tag before any PR-28 code change.
    Any deviation -- intentional or accidental -- will fail CI here.

    Skipped automatically if the case-study DB is not present (local dev without
    the full data bundle).  CI always has the DB via the repo checkout.
    """
    from pathlib import Path

    import pytest

    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "diff" / "v0.2.0_baseline.txt"
    expected = fixture_path.read_text(encoding="utf-8")

    store_path = "docs/case-studies/data/case-study-replays.db"
    baseline_id = "7e51299481d5420d9181e71ba0449348"
    candidate_id = "4332c0d246bc4b3e875392ecdf3b1780"

    if not Path(store_path).exists():
        pytest.skip(f"case-study store not found at {store_path!r}; skipping fixture check")

    args = argparse.Namespace(
        baseline_session_id=baseline_id,
        candidate_session_id=candidate_id,
        store_path=store_path,
        strict=False,
        show_timeline=False,
    )

    cli_diff.cmd_diff(args)
    captured = capsys.readouterr()
    assert captured.out == expected, (
        "Default diff output changed from v0.2.0 baseline.\n"
        "If this is intentional, re-capture the fixture from the v0.2.0 tag "
        "per the instructions in dev_notes/plans/PR-28-diff-sharpening.md §6 step 1."
    )
