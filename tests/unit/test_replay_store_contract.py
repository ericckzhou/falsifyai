"""Contract tests shared by every ReplayStore implementation.

Each test runs once per impl. The parametrization is the contract: if a new
store is added, it gets wired into the ``store`` fixture and inherits the
full test suite for free. If a test fails for one impl but not the other,
that's a contract violation in the failing impl.

Per PR #6 plan, the MVP Protocol surface is save_session / load_session /
query_sessions. case_history and diff_sessions are deferred.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from falsifyai.replay import InMemoryStore, ReplayStore, SQLiteStore
from falsifyai.replay.protocol import ReplayStoreError, SessionNotFoundError
from falsifyai.verdict.models import Verdict
from tests.fixtures.build_artifact import make_artifact


@pytest.fixture(params=["in_memory", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path) -> Iterator[ReplayStore]:
    """Fresh ReplayStore per test, parametrized over both impls."""
    if request.param == "in_memory":
        yield InMemoryStore()
    else:
        with SQLiteStore(tmp_path / "replays.db") as s:
            yield s


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------


def test_save_load_round_trip_preserves_semantic_equality(store: ReplayStore) -> None:
    artifact = make_artifact(session_id="aaaa-1111", verdict=Verdict.STABLE)
    store.save_session(artifact)
    restored = store.load_session("aaaa-1111")
    assert restored == artifact


def test_save_twice_same_session_id_raises(store: ReplayStore) -> None:
    artifact = make_artifact(session_id="dup-1")
    store.save_session(artifact)
    with pytest.raises(ReplayStoreError):
        store.save_session(artifact)


def test_load_missing_session_raises_not_found(store: ReplayStore) -> None:
    with pytest.raises(SessionNotFoundError):
        store.load_session("does-not-exist")


# ---------------------------------------------------------------------------
# Query filters
# ---------------------------------------------------------------------------


def _save_three(store: ReplayStore) -> tuple[str, str, str]:
    """Save three artifacts spaced 1 minute apart. Returns their session_ids in save order."""
    base = datetime(2026, 5, 21, 12, 0, 0, tzinfo=UTC)
    a1 = make_artifact(session_id="s1", verdict=Verdict.STABLE, created_at=base)
    a2 = make_artifact(
        session_id="s2", verdict=Verdict.FRAGILE, created_at=base + timedelta(minutes=1)
    )
    a3 = make_artifact(
        session_id="s3",
        verdict=Verdict.CONSISTENTLY_WRONG,
        created_at=base + timedelta(minutes=2),
    )
    store.save_session(a1)
    store.save_session(a2)
    store.save_session(a3)
    return "s1", "s2", "s3"


def test_query_by_spec_hash_returns_matching(store: ReplayStore) -> None:
    _save_three(store)
    results = list(store.query_sessions(spec_hash="a" * 64))
    assert {a.session_id for a in results} == {"s1", "s2", "s3"}

    results_other = list(store.query_sessions(spec_hash="nonexistent"))
    assert results_other == []


def test_query_by_case_id_returns_sessions_containing_that_case(store: ReplayStore) -> None:
    _save_three(store)
    results = list(store.query_sessions(case_id="capital_of_france"))
    assert len(results) == 3

    results_miss = list(store.query_sessions(case_id="unknown_case"))
    assert results_miss == []


def test_query_by_verdict_filters_by_session_verdict(store: ReplayStore) -> None:
    _save_three(store)
    fragile = list(store.query_sessions(verdict=Verdict.FRAGILE))
    assert [a.session_id for a in fragile] == ["s2"]

    wrong = list(store.query_sessions(verdict=Verdict.CONSISTENTLY_WRONG))
    assert [a.session_id for a in wrong] == ["s3"]


def test_query_by_since_returns_only_newer(store: ReplayStore) -> None:
    _save_three(store)
    cutoff = datetime(2026, 5, 21, 12, 0, 30, tzinfo=UTC)  # after s1
    results = list(store.query_sessions(since=cutoff))
    assert {a.session_id for a in results} == {"s2", "s3"}


def test_query_with_limit_honored(store: ReplayStore) -> None:
    _save_three(store)
    results = list(store.query_sessions(limit=2))
    assert len(results) == 2


def test_empty_store_returns_empty_iterator(store: ReplayStore) -> None:
    assert list(store.query_sessions()) == []


def test_query_with_no_filters_returns_all_newest_first(store: ReplayStore) -> None:
    _save_three(store)
    results = list(store.query_sessions())
    assert [a.session_id for a in results] == ["s3", "s2", "s1"]


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------


def test_save_is_transactional_on_serialize_error(store: ReplayStore, monkeypatch) -> None:
    """A serialize failure mid-save must leave the store empty."""
    from falsifyai.replay import serialize as _ser

    def _boom(artifact):  # noqa: ANN001
        raise RuntimeError("simulated serialize failure")

    artifact = make_artifact(session_id="will-fail")
    monkeypatch.setattr(_ser, "artifact_to_json", _boom)

    with pytest.raises(RuntimeError, match="simulated"):
        store.save_session(artifact)

    # Nothing got persisted.
    with pytest.raises(SessionNotFoundError):
        store.load_session("will-fail")
    assert list(store.query_sessions()) == []


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_store_is_a_replay_store(store: ReplayStore) -> None:
    assert isinstance(store, ReplayStore)
