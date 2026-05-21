"""Replay persistence layer.

Public surface:

- :class:`ReplayStore` — Protocol every store implementation satisfies.
- :class:`InMemoryStore` — ephemeral; useful for ad-hoc runs and as the
  test fixture for contract tests.
- :class:`SQLiteStore` — default file-backed store.
- :class:`ReplayArtifact`, :class:`CaseResult`, :class:`PerturbedRun`,
  :class:`SessionVerdict` — the persisted artifact shape.
- :class:`ReplayStoreError`, :class:`SessionNotFoundError` — exceptions.
"""

from falsifyai.replay.in_memory_store import InMemoryStore
from falsifyai.replay.models import (
    CaseResult,
    PerturbedRun,
    ReplayArtifact,
    SessionVerdict,
)
from falsifyai.replay.protocol import (
    ReplayStore,
    ReplayStoreError,
    SessionNotFoundError,
)
from falsifyai.replay.sqlite_store import SQLiteStore

__all__ = [
    "CaseResult",
    "InMemoryStore",
    "PerturbedRun",
    "ReplayArtifact",
    "ReplayStore",
    "ReplayStoreError",
    "SQLiteStore",
    "SessionNotFoundError",
    "SessionVerdict",
]
