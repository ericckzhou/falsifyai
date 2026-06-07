"""Execution layer — adapter, cache, and engine."""

from typing import TYPE_CHECKING

from falsifyai.execution.adapter import ModelAdapter
from falsifyai.execution.cache import ExecutionCache, InMemoryCache
from falsifyai.execution.engine import ExecutionEngine
from falsifyai.execution.errors import ExecutionError
from falsifyai.execution.models import Execution, ModelRequest

if TYPE_CHECKING:
    from falsifyai.execution.litellm_adapter import LiteLLMAdapter

__all__ = [
    "Execution",
    "ExecutionCache",
    "ExecutionEngine",
    "ExecutionError",
    "InMemoryCache",
    "LiteLLMAdapter",
    "ModelAdapter",
    "ModelRequest",
]


def __getattr__(name: str) -> object:
    # ``LiteLLMAdapter`` is resolved lazily (PEP 562): importing it pulls in
    # ``litellm`` — heavy, and noisy with import-time warnings. Touching any
    # execution *submodule* (e.g. ``execution.models`` via a replay artifact)
    # runs this package ``__init__``; eagerly importing the adapter here would
    # drag litellm into every read-only CLI command. Deferring it keeps
    # ``from falsifyai.execution import LiteLLMAdapter`` working while only
    # paying the cost when the adapter is actually used. Guarded by
    # tests/meta/test_cli_import_hygiene.py.
    if name == "LiteLLMAdapter":
        from falsifyai.execution.litellm_adapter import LiteLLMAdapter

        return LiteLLMAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
