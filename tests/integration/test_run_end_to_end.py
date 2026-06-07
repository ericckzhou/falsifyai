"""End-to-end integration tests for ``falsifyai run``.

These exercise the full Phase 0 chain — load_spec -> materialize -> execute ->
judge with invariants -> resolve verdict -> save artifact -> render. Real
LiteLLM is never called; ``MockAdapter`` is injected via the ``build_adapter``
test seam (decision L1).
"""

import argparse
from pathlib import Path

import pytest

import falsifyai.cli.run as cli_run
from falsifyai.replay.in_memory_store import InMemoryStore
from falsifyai.replay.sqlite_store import SQLiteStore
from falsifyai.verdict.models import Verdict
from tests.fixtures.mock_adapter import MockAdapter

_SMOKE_SPEC = Path(__file__).resolve().parents[1] / "fixtures" / "specs" / "run_smoke.yaml"


def _patch_adapter(monkeypatch: pytest.MonkeyPatch, response: str) -> MockAdapter:
    adapter = MockAdapter(default_response=response)
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)
    return adapter


def _args(spec_path: Path, store_path: str) -> argparse.Namespace:
    return argparse.Namespace(spec_path=str(spec_path), store_path=store_path)


def test_happy_path_returns_stable_and_saves_artifact(tmp_path, monkeypatch, capsys) -> None:
    adapter = _patch_adapter(monkeypatch, "Paris is the capital of France.")
    db_path = tmp_path / "replays.db"

    rc = cli_run.cmd_run(_args(_SMOKE_SPEC, str(db_path)))

    assert rc == 0  # STABLE -> SUCCESS
    captured = capsys.readouterr()
    assert "STABLE" in captured.out
    assert "capital_of_france" in captured.out

    # Adapter was called for the original + each perturbation.
    assert adapter.call_count >= 4  # 1 baseline + 3 typo perturbations

    # Artifact landed in the DB and round-trips.
    with SQLiteStore(db_path) as store:
        sessions = list(store.query_sessions())
        assert len(sessions) == 1
        loaded = sessions[0]
        assert loaded.session_verdict.session_verdict is Verdict.STABLE
        assert loaded.case_results[0].case_id == "capital_of_france"


def test_fragile_path_when_perturbation_breaks_invariant(tmp_path, monkeypatch) -> None:
    """If only the baseline mentions 'Paris' and perturbed outputs don't, FRAGILE."""
    adapter = MockAdapter(
        response_map={"What is the capital of France?": "Paris is the capital."},
        default_response="I don't know.",  # perturbed outputs hit this
    )
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    rc = cli_run.cmd_run(_args(_SMOKE_SPEC, ":memory:"))

    assert rc == 1  # FRAGILE -> DEGRADED


def test_determinism_same_seed_same_materialized_hash(tmp_path, monkeypatch) -> None:
    """Phase 0 acceptance gate item: same seed -> same materialized_hash."""
    _patch_adapter(monkeypatch, "Paris is the capital of France.")

    store1 = InMemoryStore()
    store2 = InMemoryStore()
    monkeypatch.setattr(cli_run, "build_store", lambda p: store1)
    cli_run.cmd_run(_args(_SMOKE_SPEC, ":memory:"))

    monkeypatch.setattr(cli_run, "build_store", lambda p: store2)
    cli_run.cmd_run(_args(_SMOKE_SPEC, ":memory:"))

    [a1] = list(store1.query_sessions())
    [a2] = list(store2.query_sessions())

    assert a1.materialized_hash == a2.materialized_hash
    # session_id differs (UUID per save); spec_hash should match too
    assert a1.spec_hash == a2.spec_hash
    assert a1.session_id != a2.session_id


def test_artifact_roundtrip_via_load_session(tmp_path, monkeypatch) -> None:
    _patch_adapter(monkeypatch, "Paris is the capital of France.")
    db_path = tmp_path / "replays.db"

    cli_run.cmd_run(_args(_SMOKE_SPEC, str(db_path)))

    with SQLiteStore(db_path) as store:
        [sessions] = list(store.query_sessions())
        loaded = store.load_session(sessions.session_id)

    # Semantic equality across save -> load.
    assert loaded == sessions


# ---------------------------------------------------------------------------
# Store lifecycle: run is a *producer*; it owns the store it writes to and must
# close it whether the save succeeds or raises. (Read-only consumers are covered
# by tests/unit/test_cli_store_lifecycle.py; run is kept here, with the model
# stack already mocked, so the producer/consumer boundary stays clean.)
# ---------------------------------------------------------------------------


class _TrackingStore:
    """Minimal producer-side store double: records save_session + close."""

    def __init__(self, *, fail_save: bool = False) -> None:
        self.saved: list = []
        self.closed = False
        self._fail_save = fail_save

    def save_session(self, artifact) -> None:
        if self._fail_save:
            raise RuntimeError("forced save failure")
        self.saved.append(artifact)

    def close(self) -> None:
        self.closed = True


def test_run_closes_store_after_save(monkeypatch, capsys) -> None:
    _patch_adapter(monkeypatch, "Paris is the capital of France.")
    store = _TrackingStore()
    monkeypatch.setattr(cli_run, "build_store", lambda _p: store)

    cli_run.cmd_run(_args(_SMOKE_SPEC, ":memory:"))

    assert len(store.saved) == 1
    assert store.closed is True


def test_run_closes_store_when_save_fails(monkeypatch, capsys) -> None:
    _patch_adapter(monkeypatch, "Paris is the capital of France.")
    store = _TrackingStore(fail_save=True)
    monkeypatch.setattr(cli_run, "build_store", lambda _p: store)

    with pytest.raises(RuntimeError):
        cli_run.cmd_run(_args(_SMOKE_SPEC, ":memory:"))

    assert store.closed is True
