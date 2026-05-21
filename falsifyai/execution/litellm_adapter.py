"""LiteLLM-backed sync ModelAdapter."""

import time

import litellm

from falsifyai.execution.errors import ExecutionError
from falsifyai.execution.models import Execution, ModelRequest


class LiteLLMAdapter:
    """ModelAdapter that delegates to ``litellm.completion`` (sync).

    Provider + model are concatenated into LiteLLM's ``"<provider>/<model>"``
    string format. All exceptions from LiteLLM (or a malformed response) are
    wrapped in ``ExecutionError`` with the original chained via ``__cause__``.

    No retries, no streaming, no async — Phase 0 keeps execution simple.
    """

    def execute(self, request: ModelRequest) -> Execution:
        model_string = f"{request.provider}/{request.model}"
        kwargs: dict[str, object] = {
            "model": model_string,
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "timeout": request.timeout_seconds,
        }
        if request.seed is not None:
            kwargs["seed"] = request.seed

        start = time.perf_counter()
        try:
            response = litellm.completion(**kwargs)
        except Exception as exc:
            raise ExecutionError(f"LiteLLM call failed for {model_string}: {exc}") from exc
        latency_ms = (time.perf_counter() - start) * 1000.0

        try:
            output_text = response.choices[0].message.content or ""
        except (AttributeError, IndexError) as exc:
            raise ExecutionError(f"Unexpected LiteLLM response shape: {exc}") from exc

        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage is not None else None
        completion_tokens = getattr(usage, "completion_tokens", None) if usage is not None else None

        return Execution(
            request=request,
            output_text=output_text,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached=False,
            seed_provided=request.seed is not None,
        )
