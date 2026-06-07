"""In-memory ReplayStore implementation.

Ships as a real implementation (per plan.md section 18.2) and doubles as the
test fixture for the parametrized contract suite. Uses the same JSON
serialization path as ``SQLiteStore`` so storage semantics — deep-copy
isolation, fail-fast on bad artifacts — are identical.

Not durable: dropping the process drops the data. For ephemeral runs only.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

from falsifyai.replay import serialize as _ser
from falsifyai.replay.models import ReplayArtifact
from falsifyai.replay.protocol import ReplayStoreError, SessionNotFoundError
from falsifyai.verdict.models import Verdict


@dataclass(frozen=True)
class _IndexRow:
    session_id: str
    spec_hash: str
    materialized_hash: str
    case_ids: tuple[str, ...]
    session_verdict: Verdict
    created_at: datetime


class InMemoryStore:
    def __init__(self) -> None:
        self._sessions: dict[str, str] = {}
        self._index: list[_IndexRow] = []

    def save_session(self, artifact: ReplayArtifact) -> None:
        if artifact.session_id in self._sessions:
            raise ReplayStoreError(f"duplicate session_id: {artifact.session_id}")
        # Serialize BEFORE mutating state. If this raises, nothing persists.
        encoded = _ser.artifact_to_json(artifact)
        row = _IndexRow(
            session_id=artifact.session_id,
            spec_hash=artifact.spec_hash,
            materialized_hash=artifact.materialized_hash,
            case_ids=tuple(c.case_id for c in artifact.case_results),
            session_verdict=artifact.session_verdict.session_verdict,
            created_at=artifact.created_at,
        )
        self._sessions[artifact.session_id] = encoded
        self._index.append(row)

    def load_session(self, session_id: str) -> ReplayArtifact:
        encoded = self._sessions.get(session_id)
        if encoded is None:
            raise SessionNotFoundError(session_id)
        return _ser.artifact_from_json(encoded)

    def query_sessions(
        self,
        *,
        spec_hash: str | None = None,
        case_id: str | None = None,
        verdict: Verdict | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> Iterator[ReplayArtifact]:
        rows = list(self._index)
        if spec_hash is not None:
            rows = [r for r in rows if r.spec_hash == spec_hash]
        if case_id is not None:
            rows = [r for r in rows if case_id in r.case_ids]
        if verdict is not None:
            rows = [r for r in rows if r.session_verdict is verdict]
        if since is not None:
            rows = [r for r in rows if r.created_at > since]
        rows.sort(key=lambda r: r.created_at, reverse=True)
        for r in rows[:limit]:
            yield _ser.artifact_from_json(self._sessions[r.session_id])

    def close(self) -> None:
        """No-op: nothing to release. Present so the store satisfies the
        ``ReplayStore.close`` contract and works under ``contextlib.closing``."""


def from_uri(uri: str) -> InMemoryStore:
    """Entry-point factory for the ``memory`` store scheme (``--store-path :memory:``).

    The in-memory store is ephemeral and carries no location, so ``uri`` is
    accepted for signature uniformity with other store factories and ignored.
    Registered under the ``falsifyai.stores`` group in ``pyproject.toml``.
    """
    return InMemoryStore()
