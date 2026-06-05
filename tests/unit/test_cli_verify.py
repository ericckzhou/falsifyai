"""Unit tests for ``falsifyai.cli.verify`` (PR-31).

Tests the CLI orchestration: single-session verify, --all variant, exit codes
(0 / 3 / 7), and the rendered output shape.

A ``_FakeStore`` is used so tests can serve hand-constructed artifacts —
including artifacts with intentional corruption (bad hash, tz-naive
created_at) that would be rejected at the serializer's normal save path.
"""

import argparse
import dataclasses
from collections.abc import Iterator
from datetime import datetime

import pytest

import falsifyai.cli.verify as cli_verify
from falsifyai.cli.errors import InfrastructureError
from falsifyai.replay.models import ReplayArtifact
from falsifyai.replay.protocol import SessionNotFoundError
from falsifyai.spec.materializer import compute_materialized_hash
from tests.fixtures.build_artifact import make_artifact

# ---------------------------------------------------------------------------
# Helpers — clean + corrupted artifact builders, plus a FakeStore
# ---------------------------------------------------------------------------


def _clean_artifact(session_id: str = "11111111-1111-1111-1111-111111111111") -> ReplayArtifact:
    """Build an artifact whose materialized_hash matches the recomputed value."""
    a = make_artifact(session_id=session_id)
    correct = compute_materialized_hash(a.materialized.cases)
    return dataclasses.replace(
        a,
        materialized_hash=correct,
        materialized=dataclasses.replace(a.materialized, materialized_hash=correct),
    )


_HASH_BAD_SID = "22222222-2222-2222-2222-222222222222"
_TZ_BAD_SID = "33333333-3333-3333-3333-333333333333"


def _corrupted_hash_artifact(session_id: str = _HASH_BAD_SID) -> ReplayArtifact:
    a = _clean_artifact(session_id=session_id)
    return dataclasses.replace(a, materialized_hash="0" * 64)


def _corrupted_tz_artifact(session_id: str = _TZ_BAD_SID) -> ReplayArtifact:
    a = _clean_artifact(session_id=session_id)
    return dataclasses.replace(a, created_at=datetime(2026, 5, 21, 12, 0, 0))  # naive


class _FakeStore:
    """Minimal ReplayStore stand-in. Bypasses serializer so corrupted
    artifacts can be served (the real serializer would reject naive datetimes
    at save time)."""

    def __init__(self, artifacts: list[ReplayArtifact] | None = None) -> None:
        self._artifacts: dict[str, ReplayArtifact] = {a.session_id: a for a in (artifacts or [])}

    def load_session(self, session_id: str) -> ReplayArtifact:
        if session_id not in self._artifacts:
            raise SessionNotFoundError(session_id)
        return self._artifacts[session_id]

    def query_sessions(self, **_kwargs) -> Iterator[ReplayArtifact]:
        # Newest-first ordering matches InMemoryStore.query_sessions.
        yield from sorted(self._artifacts.values(), key=lambda x: x.created_at, reverse=True)


def _args(
    session_id: str | None = None,
    *,
    all_sessions: bool = False,
    store_path: str = ":memory:",
) -> argparse.Namespace:
    return argparse.Namespace(session_id=session_id, all=all_sessions, store_path=store_path)


def _patch_store(monkeypatch, store: _FakeStore) -> _FakeStore:
    monkeypatch.setattr(cli_verify, "build_store", lambda _p: store)
    return store


# ---------------------------------------------------------------------------
# Single-session: exit codes
# ---------------------------------------------------------------------------


def test_single_clean_artifact_returns_exit_0(monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([_clean_artifact()]))
    rc = cli_verify.cmd_verify(_args("11111111-1111-1111-1111-111111111111"))
    assert rc == 0


def test_single_corrupted_hash_returns_exit_7(monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([_corrupted_hash_artifact()]))
    rc = cli_verify.cmd_verify(_args("22222222-2222-2222-2222-222222222222"))
    assert rc == 7


def test_single_corrupted_tz_returns_exit_7(monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([_corrupted_tz_artifact()]))
    rc = cli_verify.cmd_verify(_args("33333333-3333-3333-3333-333333333333"))
    assert rc == 7


def test_session_not_found_raises_infrastructure_error(monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([]))
    with pytest.raises(InfrastructureError) as excinfo:
        cli_verify.cmd_verify(_args("missing-session-id"))
    assert excinfo.value.exit_code == 3
    assert "missing-session-id" in str(excinfo.value)


def test_no_session_id_and_no_all_raises_infrastructure_error(monkeypatch) -> None:
    _patch_store(monkeypatch, _FakeStore([_clean_artifact()]))
    with pytest.raises(InfrastructureError):
        cli_verify.cmd_verify(_args(None, all_sessions=False))


# ---------------------------------------------------------------------------
# Single-session: rendered output
# ---------------------------------------------------------------------------


def test_single_verify_renders_all_8_check_rows(monkeypatch, capsys) -> None:
    _patch_store(monkeypatch, _FakeStore([_clean_artifact()]))
    cli_verify.cmd_verify(_args("11111111-1111-1111-1111-111111111111"))
    captured = capsys.readouterr()
    for name in [
        "session_id_format",
        "created_at_tz_aware",
        "materialized_hash",
        "case_count_consistency",
        "fragile_count_consistency",
        "consistently_wrong_count_consistency",
        "ci_bounds",
        "falsifiability_score_range",
    ]:
        assert name in captured.out


def test_single_verify_renders_pass_summary_footer(monkeypatch, capsys) -> None:
    _patch_store(monkeypatch, _FakeStore([_clean_artifact()]))
    cli_verify.cmd_verify(_args("11111111-1111-1111-1111-111111111111"))
    captured = capsys.readouterr()
    assert "8 checks, 8 passed, 0 failed" in captured.out
    assert "11111111-1111-1111-1111-111111111111" in captured.out


def test_single_verify_renders_failed_check_with_FAIL_marker(monkeypatch, capsys) -> None:
    _patch_store(monkeypatch, _FakeStore([_corrupted_hash_artifact()]))
    cli_verify.cmd_verify(_args("22222222-2222-2222-2222-222222222222"))
    captured = capsys.readouterr()
    assert "FAIL" in captured.out
    assert "materialized_hash" in captured.out
    assert "8 checks, 7 passed, 1 failed" in captured.out


# ---------------------------------------------------------------------------
# --all: exit codes
# ---------------------------------------------------------------------------


def test_all_with_only_clean_returns_exit_0(monkeypatch) -> None:
    store = _FakeStore(
        [
            _clean_artifact("aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa"),
            _clean_artifact("bbbbbbbb-2222-2222-2222-bbbbbbbbbbbb"),
        ]
    )
    _patch_store(monkeypatch, store)
    rc = cli_verify.cmd_verify(_args(None, all_sessions=True))
    assert rc == 0


def test_all_with_any_failure_returns_exit_7(monkeypatch) -> None:
    store = _FakeStore(
        [
            _clean_artifact("aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa"),
            _corrupted_hash_artifact("bbbbbbbb-2222-2222-2222-bbbbbbbbbbbb"),
        ]
    )
    _patch_store(monkeypatch, store)
    rc = cli_verify.cmd_verify(_args(None, all_sessions=True))
    assert rc == 7


def test_all_with_empty_store_returns_exit_0(monkeypatch, capsys) -> None:
    _patch_store(monkeypatch, _FakeStore([]))
    rc = cli_verify.cmd_verify(_args(None, all_sessions=True))
    captured = capsys.readouterr()
    assert rc == 0
    assert "no sessions" in captured.out.lower()


# ---------------------------------------------------------------------------
# --all: rendered output
# ---------------------------------------------------------------------------


def test_all_renders_per_session_section(monkeypatch, capsys) -> None:
    store = _FakeStore(
        [
            _clean_artifact("aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa"),
            _corrupted_hash_artifact("bbbbbbbb-2222-2222-2222-bbbbbbbbbbbb"),
        ]
    )
    _patch_store(monkeypatch, store)
    cli_verify.cmd_verify(_args(None, all_sessions=True))
    captured = capsys.readouterr()
    assert "aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa" in captured.out
    assert "bbbbbbbb-2222-2222-2222-bbbbbbbbbbbb" in captured.out


def test_all_renders_aggregate_footer(monkeypatch, capsys) -> None:
    store = _FakeStore(
        [
            _clean_artifact("aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa"),
            _corrupted_hash_artifact("bbbbbbbb-2222-2222-2222-bbbbbbbbbbbb"),
        ]
    )
    _patch_store(monkeypatch, store)
    cli_verify.cmd_verify(_args(None, all_sessions=True))
    captured = capsys.readouterr()
    # 2 sessions × 8 checks = 16 total. One session has 1 fail.
    assert "2 sessions" in captured.out
    assert "15 passed" in captured.out
    assert "1 failed" in captured.out


# ---------------------------------------------------------------------------
# Architectural: cmd_verify must not transitively import verdict.resolver
# ---------------------------------------------------------------------------


def test_verify_does_not_import_resolver() -> None:
    """falsifyai.cli.verify must not transitively import falsifyai.verdict.resolver.

    Mirrors test_diff_does_not_import_resolver — preservation discipline:
    verify is a pure reader of stored artifacts; it reads case.verdict from
    the artifact, never re-resolves.
    """
    import sys

    for mod_name in list(sys.modules):
        if mod_name.startswith("falsifyai.cli.verify"):
            del sys.modules[mod_name]
        if mod_name.startswith("falsifyai.integrity"):
            del sys.modules[mod_name]
        if mod_name == "falsifyai.verdict.resolver":
            del sys.modules[mod_name]

    import falsifyai.cli.verify  # noqa: F401

    assert "falsifyai.verdict.resolver" not in sys.modules, (
        "falsifyai.cli.verify must not import falsifyai.verdict.resolver "
        "(re-resolving violates the preservation guarantee). "
        "Read case.verdict from the loaded artifact instead."
    )
