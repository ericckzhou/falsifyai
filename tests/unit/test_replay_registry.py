"""Unit tests for the store registry (``falsifyai/replay/registry.py``).

Covers the scheme parser, backward-compatible built-in selection, the
``ReplayStore`` contract of what ``build_store`` returns, and plugin dispatch /
unknown-scheme failure. The entry-point *discovery* of built-ins is asserted in
``tests/meta/test_plugin_discovery.py``; here we exercise the dispatch logic.
"""

import pytest

from falsifyai.replay import registry
from falsifyai.replay.in_memory_store import InMemoryStore
from falsifyai.replay.protocol import ReplayStore
from falsifyai.replay.registry import build_store, store_scheme
from falsifyai.replay.sqlite_store import SQLiteStore


class TestStoreScheme:
    def test_memory_sentinel(self) -> None:
        assert store_scheme(":memory:") == "memory"

    def test_bare_path_defaults_to_sqlite(self) -> None:
        assert store_scheme(".falsifyai/replays.db") == "sqlite"

    def test_relative_path_defaults_to_sqlite(self) -> None:
        assert store_scheme("./out/run.db") == "sqlite"

    def test_windows_drive_letter_is_not_a_scheme(self) -> None:
        # A drive-letter colon has no `://`, so it must fall through to sqlite,
        # not be read as a `C` scheme.
        assert store_scheme(r"C:\Users\Eric\replays.db") == "sqlite"

    def test_explicit_scheme_is_extracted(self) -> None:
        assert store_scheme("postgres://host/db") == "postgres"

    def test_sqlite_uri_scheme(self) -> None:
        assert store_scheme("sqlite://./run.db") == "sqlite"


class TestBuildStoreBuiltins:
    """build_store must preserve the pre-registry path-based behavior exactly."""

    def test_memory_sentinel_builds_in_memory_store(self) -> None:
        store = build_store(":memory:")
        assert isinstance(store, InMemoryStore)

    def test_bare_path_builds_sqlite_store(self, tmp_path) -> None:
        db = tmp_path / "replays.db"
        store = build_store(str(db))
        try:
            assert isinstance(store, SQLiteStore)
            assert db.exists()  # SQLiteStore creates the file on construction
        finally:
            store.close()

    def test_sqlite_uri_strips_scheme_and_uses_path(self, tmp_path) -> None:
        db = tmp_path / "run.db"
        store = build_store(f"sqlite://{db}")
        try:
            assert isinstance(store, SQLiteStore)
            assert db.exists()
        finally:
            store.close()

    def test_returns_replaystore_compatible_object(self) -> None:
        store = build_store(":memory:")
        # The runtime-checkable protocol is the contract every backend honors.
        assert isinstance(store, ReplayStore)


class _ThirdPartyStore:
    """Stands in for a store shipped by another package (e.g. a Postgres backend)."""

    def __init__(self, uri: str) -> None:
        self.uri = uri


def _third_party_factory(uri: str) -> _ThirdPartyStore:
    return _ThirdPartyStore(uri)


class TestBuildStorePlugins:
    def test_plugin_scheme_dispatches_to_factory_with_full_uri(self, monkeypatch) -> None:
        """A registered scheme receives the *full* --store-path, scheme included.

        Backends like Postgres want the whole connection URI, not a stripped
        remainder, so build_store hands the factory the original string.
        """

        def _fake_discover() -> dict:
            return {"acme": _third_party_factory}

        monkeypatch.setattr(registry, "discover_stores", _fake_discover)
        store = build_store("acme://user@host:5432/falsify")
        assert isinstance(store, _ThirdPartyStore)
        assert store.uri == "acme://user@host:5432/falsify"

    def test_unknown_scheme_raises_with_available_list(self, monkeypatch) -> None:
        monkeypatch.setattr(registry, "discover_stores", lambda: {"sqlite": _third_party_factory})
        with pytest.raises(ValueError, match="No store backend registered for scheme 'nope'"):
            build_store("nope://whatever")
