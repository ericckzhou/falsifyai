"""In-memory execution cache for content-addressed reuse within a run.

The cache stores completed Execution records keyed by ``ModelRequest.cache_key``.
The engine layer decides when to consult it (only when ``temperature == 0``;
see plan.md section 21).
"""

from dataclasses import replace
from typing import Protocol, runtime_checkable

from falsifyai.execution.models import Execution


@runtime_checkable
class ExecutionCache(Protocol):
    def get(self, key: str) -> Execution | None: ...

    def put(self, key: str, execution: Execution) -> None: ...


class InMemoryCache:
    """Process-local dict cache. Reset between ``falsify run`` invocations.

    Returned executions are marked ``cached=True`` regardless of how they
    were originally stored, so callers can always tell hit from miss.
    """

    def __init__(self) -> None:
        self._store: dict[str, Execution] = {}

    def get(self, key: str) -> Execution | None:
        hit = self._store.get(key)
        if hit is None:
            return None
        return replace(hit, cached=True)

    def put(self, key: str, execution: Execution) -> None:
        self._store[key] = execution
