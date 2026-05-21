"""Tests for falsifyai.execution.engine.ExecutionEngine."""

from falsifyai.execution.cache import InMemoryCache
from falsifyai.execution.engine import ExecutionEngine
from falsifyai.execution.models import ModelRequest
from tests.fixtures.mock_adapter import MockAdapter


def _req(temperature: float = 0.0, prompt: str = "Hi.") -> ModelRequest:
    return ModelRequest(
        provider="openai",
        model="gpt-4o-mini",
        prompt=prompt,
        temperature=temperature,
        max_tokens=128,
        seed=None,
        timeout_seconds=30,
    )


def test_engine_without_cache_calls_adapter() -> None:
    adapter = MockAdapter(response_map={"Hi.": "Hello"})
    engine = ExecutionEngine(adapter)
    result = engine.execute(_req())
    assert result.output_text == "Hello"
    assert adapter.call_count == 1
    assert result.cached is False


def test_engine_misses_then_caches_on_temperature_zero() -> None:
    adapter = MockAdapter(response_map={"Hi.": "Hello"})
    cache = InMemoryCache()
    engine = ExecutionEngine(adapter, cache=cache)
    first = engine.execute(_req(temperature=0.0))
    assert adapter.call_count == 1
    assert first.cached is False


def test_engine_returns_cached_on_temperature_zero_hit() -> None:
    adapter = MockAdapter(response_map={"Hi.": "Hello"})
    cache = InMemoryCache()
    engine = ExecutionEngine(adapter, cache=cache)
    first = engine.execute(_req(temperature=0.0))
    second = engine.execute(_req(temperature=0.0))
    assert adapter.call_count == 1  # second call hit cache, not adapter
    assert first.cached is False
    assert second.cached is True
    assert second.output_text == first.output_text


def test_engine_skips_cache_when_temperature_nonzero() -> None:
    adapter = MockAdapter(response_map={"Hi.": "Hello"})
    cache = InMemoryCache()
    engine = ExecutionEngine(adapter, cache=cache)
    engine.execute(_req(temperature=0.5))
    engine.execute(_req(temperature=0.5))
    assert adapter.call_count == 2  # both calls hit adapter
    assert cache.get(_req(temperature=0.5).cache_key) is None  # nothing stored


def test_engine_returns_distinct_outputs_for_distinct_prompts() -> None:
    adapter = MockAdapter(response_map={"A": "alpha", "B": "beta"})
    engine = ExecutionEngine(adapter, cache=InMemoryCache())
    a = engine.execute(_req(prompt="A"))
    b = engine.execute(_req(prompt="B"))
    assert a.output_text == "alpha"
    assert b.output_text == "beta"
    assert adapter.call_count == 2
