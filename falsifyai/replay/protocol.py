"""ReplayStore Protocol and its exception hierarchy.

The Protocol is the contract every store implementation must satisfy. Two
impls ship in PR #6: ``InMemoryStore`` (ephemeral, also useful as a test
double) and ``SQLiteStore`` (default; file-backed at ``.falsify/replays.db``).

MVP surface only — ``case_history`` and ``diff_sessions`` from plan.md
section 18.1 are deferred to the Week 2 PRs that introduce ``falsify diff``
and verdict-history queries.
"""

from collections.abc import Iterator
from datetime import datetime
from typing import Protocol, runtime_checkable

from falsifyai.replay.models import ReplayArtifact
from falsifyai.verdict.models import Verdict


class ReplayStoreError(Exception):
    """Base error for replay store operations (serialization, persistence)."""


class SessionNotFoundError(ReplayStoreError):
    """Raised by ``load_session`` when no session matches the given id."""


@runtime_checkable
class ReplayStore(Protocol):
    """Persistence contract for replay artifacts.

    Implementations must guarantee:
    - ``save_session`` is atomic: a failed save leaves the store unchanged.
    - ``save_session`` rejects a second save with the same ``session_id``
      (raises ``ReplayStoreError``).
    - ``load_session`` raises ``SessionNotFoundError`` for unknown ids.
    - ``query_sessions`` yields artifacts newest-first by ``created_at``.
    """

    def save_session(self, artifact: ReplayArtifact) -> None: ...

    def load_session(self, session_id: str) -> ReplayArtifact: ...

    def query_sessions(
        self,
        *,
        spec_hash: str | None = None,
        case_id: str | None = None,
        verdict: Verdict | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> Iterator[ReplayArtifact]: ...
