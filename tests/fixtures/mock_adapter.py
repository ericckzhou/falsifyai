"""Reusable MockAdapter for tests. Per plan.md section 23.2.

Programmable: maps prompts -> output text (or a callable for dynamic
behavior). Records every call for assertions.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from falsifyai.execution.models import Execution, ModelRequest


@dataclass
class MockAdapter:
    """Deterministic ModelAdapter substitute for tests."""

    response_map: dict[str, str | Callable[[str], str]] = field(default_factory=dict)
    default_response: str = ""
    latency_ms: float = 1.0
    calls: list[ModelRequest] = field(default_factory=list)

    def execute(self, request: ModelRequest) -> Execution:
        self.calls.append(request)
        responder = self.response_map.get(request.prompt, self.default_response)
        output = responder(request.prompt) if callable(responder) else responder
        return Execution(
            request=request,
            output_text=output,
            latency_ms=self.latency_ms,
            prompt_tokens=len(request.prompt.split()),
            completion_tokens=len(output.split()),
            cached=False,
            seed_provided=request.seed is not None,
        )

    @property
    def call_count(self) -> int:
        return len(self.calls)
