"""Execution data models — immutable records of a model invocation."""

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRequest:
    """A deterministic description of one model invocation.

    Frozen so callers can hash, use as dict keys, or pass across threads
    without worrying about mutation.
    """

    provider: str
    model: str
    prompt: str
    temperature: float
    max_tokens: int
    seed: int | None
    timeout_seconds: int

    @property
    def cache_key(self) -> str:
        """sha256 content-addressed key for the execution cache.

        Excludes `temperature` and `seed` by design: cache lookup is gated
        by ``temperature == 0`` at the engine layer, so every keyed request
        is implicitly deterministic. See plan.md section 21.
        """
        payload = "\x1f".join(
            [
                self.provider,
                self.model,
                self.prompt,
                str(self.max_tokens),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Execution:
    """The result of running one ModelRequest through a ModelAdapter."""

    request: ModelRequest
    output_text: str
    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    cached: bool
    seed_provided: bool
