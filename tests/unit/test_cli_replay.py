"""Tests for falsifyai.cli.replay — the read-only consumer surface.

Exercises the replay command in isolation: load_session vs --latest, error
paths, exit-code mirroring, and the read-only invariant.
"""

import argparse

import pytest

from falsifyai.cli import replay as replay_module
from falsifyai.cli.errors import CLIError
from falsifyai.replay.in_memory_store import InMemoryStore
from falsifyai.verdict.models import Verdict
from tests.fixtures.build_artifact import make_artifact


def _args(session_id: str | None = None, *, latest: bool = False, store_path: str = ":memory:"):
    return argparse.Namespace(session_id=session_id, latest=latest, store_path=store_path)


def _patched_store(monkeypatch: pytest.MonkeyPatch, store: InMemoryStore) -> InMemoryStore:
    """Replace _build_store so cmd_replay sees the fixture-populated store."""
    monkeypatch.setattr(replay_module, "_build_store", lambda _path: store)
    return store


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_load_by_session_id_succeeds(monkeypatch, capsys) -> None:
    store = InMemoryStore()
    store.save_session(make_artifact(session_id="sess-X", verdict=Verdict.STABLE))
    _patched_store(monkeypatch, store)

    rc = replay_module.cmd_replay(_args(session_id="sess-X"))
    assert rc == 0
    captured = capsys.readouterr()
    assert "sess-X" in captured.out
    assert "Loaded session" in captured.out
    assert "STABLE" in captured.out


def test_latest_with_single_session_loads_it(monkeypatch, capsys) -> None:
    store = InMemoryStore()
    store.save_session(make_artifact(session_id="only-one", verdict=Verdict.FRAGILE))
    _patched_store(monkeypatch, store)

    rc = replay_module.cmd_replay(_args(latest=True))
    assert rc == 1  # FRAGILE -> DEGRADED
    captured = capsys.readouterr()
    assert "only-one" in captured.out


def test_latest_with_multiple_sessions_picks_newest(monkeypatch, capsys) -> None:
    from datetime import UTC, datetime, timedelta

    store = InMemoryStore()
    base = datetime(2026, 5, 21, 12, 0, 0, tzinfo=UTC)
    store.save_session(make_artifact(session_id="older", created_at=base))
    store.save_session(make_artifact(session_id="newer", created_at=base + timedelta(minutes=5)))
    _patched_store(monkeypatch, store)

    rc = replay_module.cmd_replay(_args(latest=True))
    assert rc == 0
    captured = capsys.readouterr()
    assert "newer" in captured.out
    assert "older" not in captured.out


# ---------------------------------------------------------------------------
# Exit codes mirror run
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "verdict, expected_code",
    [
        (Verdict.STABLE, 0),
        (Verdict.FRAGILE, 1),
        (Verdict.CONSISTENTLY_WRONG, 2),
    ],
)
def test_exit_code_mirrors_session_verdict(monkeypatch, verdict, expected_code) -> None:
    store = InMemoryStore()
    store.save_session(make_artifact(session_id="sess", verdict=verdict))
    _patched_store(monkeypatch, store)

    rc = replay_module.cmd_replay(_args(session_id="sess"))
    assert rc == expected_code


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_missing_session_id_raises_cli_error(monkeypatch) -> None:
    store = InMemoryStore()
    _patched_store(monkeypatch, store)

    with pytest.raises(CLIError) as exc_info:
        replay_module.cmd_replay(_args(session_id="nope"))
    assert exc_info.value.exit_code == 3
    assert "nope" in str(exc_info.value)


def test_latest_with_empty_store_raises_cli_error(monkeypatch) -> None:
    store = InMemoryStore()
    _patched_store(monkeypatch, store)

    with pytest.raises(CLIError) as exc_info:
        replay_module.cmd_replay(_args(latest=True))
    assert exc_info.value.exit_code == 3
    assert "no sessions" in str(exc_info.value).lower()


def test_neither_session_id_nor_latest_raises_cli_error(monkeypatch) -> None:
    """argparse should normally prevent this; defensive check in cmd_replay."""
    store = InMemoryStore()
    _patched_store(monkeypatch, store)

    with pytest.raises(CLIError) as exc_info:
        replay_module.cmd_replay(_args(session_id=None, latest=False))
    assert exc_info.value.exit_code == 3


# ---------------------------------------------------------------------------
# Read-only invariant: cmd_replay never modifies the store
# ---------------------------------------------------------------------------


def test_replay_does_not_modify_the_artifact(monkeypatch) -> None:
    store = InMemoryStore()
    original = make_artifact(session_id="readonly-check", verdict=Verdict.STABLE)
    store.save_session(original)
    _patched_store(monkeypatch, store)

    replay_module.cmd_replay(_args(session_id="readonly-check"))

    # Load again; must be byte-identical to the original.
    after = store.load_session("readonly-check")
    assert after == original
