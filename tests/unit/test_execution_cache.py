"""Tests for falsifyai.execution.cache.InMemoryCache."""

from falsifyai.execution.cache import InMemoryCache
from falsifyai.execution.models import Execution, ModelRequest


def _execution(prompt: str = "hi", cached: bool = False) -> Execution:
    return Execution(
        request=ModelRequest(
            provider="openai",
            model="gpt-4o-mini",
            prompt=prompt,
            temperature=0.0,
            max_tokens=128,
            seed=None,
            timeout_seconds=30,
        ),
        output_text="hello",
        latency_ms=5.0,
        prompt_tokens=1,
        completion_tokens=1,
        cached=cached,
        seed_provided=False,
    )


def test_get_returns_none_for_unseen_key() -> None:
    cache = InMemoryCache()
    assert cache.get("missing") is None


def test_put_then_get_round_trips_output() -> None:
    cache = InMemoryCache()
    ex = _execution()
    cache.put(ex.request.cache_key, ex)
    got = cache.get(ex.request.cache_key)
    assert got is not None
    assert got.output_text == ex.output_text
    assert got.request == ex.request


def test_get_marks_result_as_cached_even_when_put_was_not() -> None:
    cache = InMemoryCache()
    ex = _execution(cached=False)
    cache.put(ex.request.cache_key, ex)
    got = cache.get(ex.request.cache_key)
    assert got is not None
    assert got.cached is True


def test_distinct_keys_do_not_collide() -> None:
    cache = InMemoryCache()
    a = _execution(prompt="A")
    b = _execution(prompt="B")
    cache.put(a.request.cache_key, a)
    cache.put(b.request.cache_key, b)
    assert a.request.cache_key != b.request.cache_key
    assert cache.get(a.request.cache_key) is not None
    assert cache.get(b.request.cache_key) is not None
