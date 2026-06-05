"""Map a ``--store-path`` value to a runtime :class:`ReplayStore`.

Dispatch mirrors the perturbation and invariant registries (decision 1A), one
tier below the three evidence layers: a registry is *assembly/wiring*
infrastructure — it decides which object to construct, never what that object
does. Selecting a SQLite file versus a Postgres backend changes where evidence
is preserved, not how it is generated or interpreted, so this stays cleanly in
the preservation layer.

- **Built-ins** ship two schemes — ``sqlite`` (the default) and ``memory``
  (``--store-path :memory:``) — and are registered as entry points in
  ``pyproject.toml``, so the discovery mechanism is dogfooded rather than
  special-cased for third parties only.
- **Plugins** register a factory under the ``falsifyai.stores`` entry-point
  group keyed by the URI scheme they handle. A Postgres store ships
  ``postgres = mypkg.store:from_uri`` and users select it with
  ``--store-path postgres://host/db`` — no fork required. This is the
  out-of-tree path for ``PostgresStore`` / ``S3Store`` (plan.md section 18.4).

A store factory is any callable ``(uri: str) -> ReplayStore``. It receives the
full ``--store-path`` string (including any ``scheme://`` prefix) and parses
whatever it needs; built-in factories live next to their implementations
(``in_memory_store.from_uri``, ``sqlite_store.from_uri``).
"""

from collections.abc import Callable
from importlib.metadata import entry_points

from falsifyai.replay.protocol import ReplayStore

_ENTRY_POINT_GROUP = "falsifyai.stores"

StoreFactory = Callable[[str], ReplayStore]


def discover_stores() -> dict[str, StoreFactory]:
    """Return ``{scheme: factory}`` for every store registered via entry points.

    Reads the ``falsifyai.stores`` group from installed package metadata.
    Built-ins (``sqlite``, ``memory``) are registered there too, so this is the
    single source of truth for "what store backends exist", including plugins.
    """
    return {ep.name: ep.load() for ep in entry_points(group=_ENTRY_POINT_GROUP)}


def store_scheme(store_path: str) -> str:
    """Return the store scheme a ``--store-path`` value selects.

    - ``:memory:`` -> ``memory``
    - an explicit ``scheme://...`` -> that ``scheme``
    - anything else (a bare filesystem path) -> the default ``sqlite``

    A bare Windows path (``C:\\replays.db``) is *not* read as a scheme: it has a
    drive-letter colon but no ``://``, so it falls through to ``sqlite``.
    """
    if store_path == ":memory:":
        return "memory"
    if "://" in store_path:
        return store_path.split("://", 1)[0]
    return "sqlite"


def build_store(store_path: str) -> ReplayStore:
    """Construct the ``ReplayStore`` selected by ``store_path``.

    The single store-construction entry point for every CLI command. Backward
    compatible: ``:memory:`` -> ephemeral in-memory store, a bare path ->
    SQLite at that path. A ``scheme://`` URI dispatches to the plugin registered
    under ``scheme``; the full original value is handed to the factory.

    Raises:
        ValueError: if ``store_path`` names a scheme with no registered store
            backend (mirrors ``build_perturbation`` / ``build_invariant`` on an
            unknown plugin name).
    """
    scheme = store_scheme(store_path)
    registry = discover_stores()
    factory = registry.get(scheme)
    if factory is None:
        raise ValueError(
            f"No store backend registered for scheme {scheme!r} "
            f"(from --store-path {store_path!r}). Available: {sorted(registry)}"
        )
    return factory(store_path)
