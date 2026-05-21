"""SQLite-backed ReplayStore implementation.

Schema (version 1):

- ``sessions``: one row per save_session. Indexed on ``spec_hash``,
  ``session_verdict``, ``created_at_iso``. Holds the full artifact JSON in
  ``payload_json`` — single source of truth on load.
- ``case_results``: one row per case in a session. Denormalized index used
  exclusively for ``query_sessions(case_id=...)`` lookups. ``payload_json``
  is NOT duplicated here.
- ``schema_meta``: a single-row table holding the schema version. Refuses to
  open a database with a version higher than this code understands. See
  PR #6 plan decision J1.

WAL is enabled on open for better concurrent-reader behavior.

Atomicity: ``save_session`` wraps both inserts in one transaction. A failure
mid-save rolls back; partial writes are impossible.
"""

import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from falsifyai.replay import serialize as _ser
from falsifyai.replay.models import ReplayArtifact
from falsifyai.replay.protocol import ReplayStoreError, SessionNotFoundError
from falsifyai.verdict.models import Verdict

SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id        TEXT PRIMARY KEY,
    spec_hash         TEXT NOT NULL,
    materialized_hash TEXT NOT NULL,
    session_verdict   TEXT NOT NULL,
    falsifyai_version TEXT NOT NULL,
    created_at_iso    TEXT NOT NULL,
    payload_json      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_spec_hash   ON sessions(spec_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_verdict     ON sessions(session_verdict);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at  ON sessions(created_at_iso);

CREATE TABLE IF NOT EXISTS case_results (
    session_id   TEXT NOT NULL,
    case_id      TEXT NOT NULL,
    case_verdict TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_case_results_case_id ON case_results(case_id);
CREATE INDEX IF NOT EXISTS idx_case_results_verdict ON case_results(case_verdict);
"""


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # ``isolation_level=None`` -> we manage transactions explicitly.
        self._conn = sqlite3.connect(str(self._path), isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._initialize_schema()

    # -------------------------------------------------------------------
    # Context manager
    # -------------------------------------------------------------------

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.close()

    def close(self) -> None:
        self._conn.close()

    # -------------------------------------------------------------------
    # Schema
    # -------------------------------------------------------------------

    def _initialize_schema(self) -> None:
        self._conn.executescript(_SCHEMA_SQL)
        row = self._conn.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
        if row is None:
            self._conn.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))
        else:
            (existing,) = row
            if existing > SCHEMA_VERSION:
                # Close before raising so the caller's ``except`` doesn't leak the conn.
                self._conn.close()
                raise ReplayStoreError(
                    f"database schema version {existing} is newer than this build "
                    f"understands (max {SCHEMA_VERSION}). Upgrade falsifyai."
                )

    # -------------------------------------------------------------------
    # Save / load
    # -------------------------------------------------------------------

    def save_session(self, artifact: ReplayArtifact) -> None:
        existing = self._conn.execute(
            "SELECT 1 FROM sessions WHERE session_id = ?", (artifact.session_id,)
        ).fetchone()
        if existing is not None:
            raise ReplayStoreError(f"duplicate session_id: {artifact.session_id}")

        # Serialize BEFORE BEGIN so a serialization failure never opens a transaction.
        payload = _ser.artifact_to_json(artifact)

        self._conn.execute("BEGIN")
        try:
            self._conn.execute(
                """INSERT INTO sessions
                   (session_id, spec_hash, materialized_hash, session_verdict,
                    falsifyai_version, created_at_iso, payload_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    artifact.session_id,
                    artifact.spec_hash,
                    artifact.materialized_hash,
                    artifact.session_verdict.session_verdict.value,
                    artifact.falsifyai_version,
                    artifact.created_at.isoformat(),
                    payload,
                ),
            )
            self._conn.executemany(
                "INSERT INTO case_results (session_id, case_id, case_verdict) VALUES (?, ?, ?)",
                [(artifact.session_id, c.case_id, c.verdict.value) for c in artifact.case_results],
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def load_session(self, session_id: str) -> ReplayArtifact:
        row = self._conn.execute(
            "SELECT payload_json FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise SessionNotFoundError(session_id)
        (payload,) = row
        return _ser.artifact_from_json(payload)

    # -------------------------------------------------------------------
    # Query
    # -------------------------------------------------------------------

    def query_sessions(
        self,
        *,
        spec_hash: str | None = None,
        case_id: str | None = None,
        verdict: Verdict | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> Iterator[ReplayArtifact]:
        clauses: list[str] = []
        params: list[object] = []

        if case_id is not None:
            clauses.append(
                "session_id IN (SELECT DISTINCT session_id FROM case_results WHERE case_id = ?)"
            )
            params.append(case_id)
        if spec_hash is not None:
            clauses.append("spec_hash = ?")
            params.append(spec_hash)
        if verdict is not None:
            clauses.append("session_verdict = ?")
            params.append(verdict.value)
        if since is not None:
            clauses.append("created_at_iso > ?")
            params.append(since.isoformat())

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT payload_json FROM sessions {where} ORDER BY created_at_iso DESC LIMIT ?"
        params.append(limit)

        for (payload,) in self._conn.execute(sql, params):
            yield _ser.artifact_from_json(payload)
