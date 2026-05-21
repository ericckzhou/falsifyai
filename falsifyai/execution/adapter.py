"""ModelAdapter Protocol — the interface every model backend implements."""

from typing import Protocol, runtime_checkable

from falsifyai.execution.models import Execution, ModelRequest


@runtime_checkable
class ModelAdapter(Protocol):
    """Executes a single ModelRequest and returns a structured Execution.

    Implementations must raise ``ExecutionError`` on any failure rather than
    leaking provider-specific exception types.
    """

    def execute(self, request: ModelRequest) -> Execution: ...
