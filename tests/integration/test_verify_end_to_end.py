"""End-to-end integration tests for ``falsifyai verify``.

Proves the run -> save -> verify chain. A real ``cmd_run`` invocation
against the smoke spec, saved to an on-disk SQLiteStore, should pass
all 8 integrity checks under ``cmd_verify``.

A second test mutates the saved JSON payload to corrupt the
``materialized_hash`` and confirms ``cmd_verify`` returns exit 7 — proves
the integrity check actually inspects what the store returns, not stale
in-memory values.
"""

import argparse
import json
from pathlib import Path

import falsifyai.cli.run as cli_run
import falsifyai.cli.verify as cli_verify
from falsifyai.replay.sqlite_store import SQLiteStore
from tests.fixtures.mock_adapter import MockAdapter

_SMOKE_SPEC = Path(__file__).resolve().parents[1] / "fixtures" / "specs" / "run_smoke.yaml"


def _run_args(spec_path: Path, store_path: str) -> argparse.Namespace:
    return argparse.Namespace(spec_path=str(spec_path), store_path=store_path)


def _verify_args(
    session_id: str | None,
    store_path: str,
    *,
    all_sessions: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(session_id=session_id, all=all_sessions, store_path=store_path)


def _do_one_run(store_path: str, response: str = "Paris is the capital of France.") -> str:
    """Run cmd_run with a MockAdapter and return the new session id."""
    import falsifyai.cli.run as cli_run_mod

    adapter = MockAdapter(default_response=response)
    orig_build = cli_run_mod.build_adapter
    cli_run_mod.build_adapter = lambda model: adapter  # type: ignore[assignment]
    try:
        cli_run.cmd_run(_run_args(_SMOKE_SPEC, store_path))
    finally:
        cli_run_mod.build_adapter = orig_build  # type: ignore[assignment]

    with SQLiteStore(store_path) as store:
        latest = next(iter(store.query_sessions(limit=1)))
    return latest.session_id


# ---------------------------------------------------------------------------
# Happy path: full pipeline returns exit 0
# ---------------------------------------------------------------------------


def test_verify_clean_run_returns_exit_0(tmp_path, capsys) -> None:
    db_path = str(tmp_path / "replays.db")
    session_id = _do_one_run(db_path)
    capsys.readouterr()  # drop the cmd_run output

    rc = cli_verify.cmd_verify(_verify_args(session_id, db_path))
    captured = capsys.readouterr()

    assert rc == 0
    assert "8 checks, 8 passed, 0 failed" in captured.out
    assert session_id in captured.out


def test_verify_all_with_two_clean_runs_returns_exit_0(tmp_path, capsys) -> None:
    db_path = str(tmp_path / "replays.db")
    _do_one_run(db_path)
    _do_one_run(db_path)
    capsys.readouterr()

    rc = cli_verify.cmd_verify(_verify_args(None, db_path, all_sessions=True))
    captured = capsys.readouterr()

    assert rc == 0
    assert "2 sessions" in captured.out


# ---------------------------------------------------------------------------
# Mutation: corrupt the stored payload, confirm exit 7
# ---------------------------------------------------------------------------


def test_verify_detects_materialized_hash_mutation(tmp_path, capsys) -> None:
    """Mutate the saved JSON's materialized_hash field and assert verify catches it.

    Proves the integrity check works on data the store actually returned,
    not on a passed-in in-memory artifact.
    """
    import sqlite3

    db_path = str(tmp_path / "replays.db")
    session_id = _do_one_run(db_path)
    capsys.readouterr()

    # Directly mutate the stored JSON payload to corrupt the materialized_hash.
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT payload_json FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        assert row is not None, "session not found in sqlite store"
        payload = json.loads(row[0])
        payload["materialized_hash"] = "0" * 64
        conn.execute(
            "UPDATE sessions SET payload_json = ? WHERE session_id = ?",
            (json.dumps(payload), session_id),
        )
        conn.commit()

    rc = cli_verify.cmd_verify(_verify_args(session_id, db_path))
    captured = capsys.readouterr()

    assert rc == 7
    assert "materialized_hash" in captured.out
    assert "FAIL" in captured.out


# ---------------------------------------------------------------------------
# CLI dispatch: end-to-end through cli/main.py argparse
# ---------------------------------------------------------------------------


def test_verify_via_main_cli_returns_exit_0(tmp_path, capsys) -> None:
    """End-to-end through cli/main.py argparse dispatch."""
    import falsifyai.cli.main as cli_main

    db_path = str(tmp_path / "replays.db")
    session_id = _do_one_run(db_path)
    capsys.readouterr()

    rc = cli_main.main(["verify", session_id, "--store-path", db_path])
    assert rc == 0


def test_verify_all_via_main_cli_with_empty_store_returns_exit_0(tmp_path, capsys) -> None:
    import falsifyai.cli.main as cli_main

    db_path = str(tmp_path / "replays.db")
    # Create an empty store by opening + closing.
    SQLiteStore(db_path).close()

    rc = cli_main.main(["verify", "--all", "--store-path", db_path])
    captured = capsys.readouterr()
    assert rc == 0
    assert "no sessions" in captured.out.lower()
