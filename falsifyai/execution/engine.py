"""ExecutionEngine — orchestrates ModelAdapter + ExecutionCache."""

from falsifyai.execution.adapter import ModelAdapter
from falsifyai.execution.cache import ExecutionCache
from falsifyai.execution.models import Execution, ModelRequest


class ExecutionEngine:
    """Runs ModelRequests through an adapter, optionally caching.

    Caching is content-addressed (by ``request.cache_key``) and ONLY applies
    when ``request.temperature == 0``. With ``temperature > 0`` every call
    hits the adapter — this is intentional, so perturbation testing observes
    real variance (plan.md sections 21, 25.4).
    """

    def __init__(
        self,
        adapter: ModelAdapter,
        cache: ExecutionCache | None = None,
    ) -> None:
        self._adapter = adapter
        self._cache = cache

    def execute(self, request: ModelRequest) -> Execution:
        cache = self._cache if request.temperature == 0 else None
        if cache is not None:
            hit = cache.get(request.cache_key)
            if hit is not None:
                return hit

        execution = self._adapter.execute(request)
        if cache is not None:
            cache.put(request.cache_key, execution)
        return execution
