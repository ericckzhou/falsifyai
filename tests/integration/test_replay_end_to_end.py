"""End-to-end integration tests for ``falsifyai replay``.

Proves the load → render path against artifacts actually produced by
``cmd_run``. Uses a real ``SQLiteStore`` (via tmp_path) and a real
``MockAdapter`` injection seam — same pattern as test_run_end_to_end.py.
"""

import argparse
from pathlib import Path

import falsifyai.cli.replay as cli_replay
import falsifyai.cli.run as cli_run
from falsifyai.replay.sqlite_store import SQLiteStore
from tests.fixtures.mock_adapter import MockAdapter

_SMOKE_SPEC = Path(__file__).resolve().parents[1] / "fixtures" / "specs" / "run_smoke.yaml"


def _run_args(spec_path: Path, store_path: str) -> argparse.Namespace:
    return argparse.Namespace(spec_path=str(spec_path), store_path=store_path)


def _replay_args(
    session_id: str | None = None, *, latest: bool = False, store_path: str = ":memory:"
) -> argparse.Namespace:
    return argparse.Namespace(session_id=session_id, latest=latest, store_path=store_path)


def test_run_then_replay_latest_round_trips(tmp_path, monkeypatch, capsys) -> None:
    """`falsifyai run` writes a session; `falsifyai replay --latest` reads it back."""
    adapter = MockAdapter(default_response="Paris is the capital of France.")
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    db_path = tmp_path / "replays.db"
    run_rc = cli_run.cmd_run(_run_args(_SMOKE_SPEC, str(db_path)))
    assert run_rc == 0  # STABLE

    # Discard the run output and replay the latest.
    capsys.readouterr()

    replay_rc = cli_replay.cmd_replay(_replay_args(latest=True, store_path=str(db_path)))
    assert replay_rc == 0  # mirrors run's exit code
    captured = capsys.readouterr()
    assert "Loaded session" in captured.out
    assert "STABLE" in captured.out


def test_replay_after_two_runs_picks_newest(tmp_path, monkeypatch) -> None:
    """--latest must select the most recent session by created_at."""
    adapter = MockAdapter(default_response="Paris is the capital of France.")
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    db_path = tmp_path / "replays.db"
    cli_run.cmd_run(_run_args(_SMOKE_SPEC, str(db_path)))
    cli_run.cmd_run(_run_args(_SMOKE_SPEC, str(db_path)))

    # Inspect the store directly to find the newer session_id.
    with SQLiteStore(db_path) as store:
        sessions = list(store.query_sessions(limit=2))
        assert len(sessions) == 2
        newest = sessions[0]  # query_sessions returns newest-first

    # `--latest` must load the same one.
    import io

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    cli_replay.cmd_replay(_replay_args(latest=True, store_path=str(db_path)))
    monkeypatch.undo()

    assert newest.session_id in buf.getvalue()


def test_replay_with_wrong_session_id_exits_three_via_main(monkeypatch) -> None:
    """End-to-end: CLI main catches the InfrastructureError and returns 3."""
    import falsifyai.cli.main as cli_main

    rc = cli_main.main(["replay", "definitely-not-a-real-session", "--store-path", ":memory:"])
    assert rc == 3
