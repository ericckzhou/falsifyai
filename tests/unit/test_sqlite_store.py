"""SQLite-specific tests not covered by the parametrized contract suite.

Schema layout, indexes, WAL mode, reopen behavior, parent-directory creation,
and the forward-compat version refusal all live here. Behavior shared with
``InMemoryStore`` (save/load/query semantics) lives in
``test_replay_store_contract.py``.
"""

import sqlite3
from contextlib import closing

import pytest

from falsifyai.replay.protocol import ReplayStoreError
from falsifyai.replay.sqlite_store import SCHEMA_VERSION, SQLiteStore
from tests.fixtures.build_artifact import make_artifact


def test_schema_version_written_on_first_open(tmp_path) -> None:
    db_path = tmp_path / "replays.db"
    with SQLiteStore(db_path):
        pass
    with closing(sqlite3.connect(db_path)) as conn:
        (version,) = conn.execute("SELECT version FROM schema_meta").fetchone()
        assert version == SCHEMA_VERSION


def test_reopening_existing_file_preserves_data(tmp_path) -> None:
    db_path = tmp_path / "replays.db"
    artifact = make_artifact(session_id="reopen-1")
    with SQLiteStore(db_path) as s:
        s.save_session(artifact)
    # Reopen.
    with SQLiteStore(db_path) as s2:
        restored = s2.load_session("reopen-1")
        assert restored == artifact


def test_refuses_to_open_db_with_higher_schema_version(tmp_path) -> None:
    """Pre-populate a DB with version SCHEMA_VERSION + 1; open must raise."""
    db_path = tmp_path / "replays.db"
    # Create a baseline DB first so schema exists.
    SQLiteStore(db_path).close()
    # Bump version under the floor.
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("UPDATE schema_meta SET version = ?", (SCHEMA_VERSION + 5,))
        conn.commit()
    with pytest.raises(ReplayStoreError, match="newer than this build"):
        SQLiteStore(db_path)


def test_wal_mode_enabled(tmp_path) -> None:
    db_path = tmp_path / "replays.db"
    with SQLiteStore(db_path), closing(sqlite3.connect(db_path)) as conn:
        (mode,) = conn.execute("PRAGMA journal_mode").fetchone()
        assert mode.lower() == "wal"


def test_expected_indexes_exist(tmp_path) -> None:
    """All indexes called out in the schema must actually exist after init."""
    db_path = tmp_path / "replays.db"
    expected = {
        "idx_sessions_spec_hash",
        "idx_sessions_verdict",
        "idx_sessions_created_at",
        "idx_case_results_case_id",
        "idx_case_results_verdict",
    }
    with SQLiteStore(db_path), closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        names = {n for (n,) in rows}
    assert expected.issubset(names)


def test_parent_directory_created_when_missing(tmp_path) -> None:
    nested = tmp_path / "deep" / "nested" / "replays.db"
    assert not nested.parent.exists()
    with SQLiteStore(nested):
        pass
    assert nested.exists()


def test_context_manager_closes_connection(tmp_path) -> None:
    db_path = tmp_path / "replays.db"
    store = SQLiteStore(db_path)
    with store:
        store.save_session(make_artifact(session_id="ctx-1"))
    # After context exit the connection is closed; any op should fail.
    with pytest.raises(sqlite3.ProgrammingError):
        store.load_session("ctx-1")


# Note: the in-transaction ROLLBACK path of ``save_session`` (the executemany
# failure branch) is intentionally not unit-tested. ``sqlite3.Connection``
# rejects monkey-patching its C-defined methods, so simulating a mid-
# transaction failure requires either a custom Connection subclass or full
# DB-level fault injection -- both heavy for the small risk reduction. The
# pre-transaction failure path is covered by
# ``test_save_is_transactional_on_serialize_error`` in the contract suite;
# the in-transaction path is a textbook try/except/raise.


def test_two_stores_can_open_same_file(tmp_path) -> None:
    """WAL mode + same-file open should not deadlock or corrupt."""
    db_path = tmp_path / "replays.db"
    with SQLiteStore(db_path) as a:
        a.save_session(make_artifact(session_id="multi-1"))
        with SQLiteStore(db_path) as b:
            restored = b.load_session("multi-1")
            assert restored.session_id == "multi-1"
