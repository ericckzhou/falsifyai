"""Tests for falsifyai.execution.models."""

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from falsifyai.execution.models import Execution, ModelRequest


def _req(**overrides: Any) -> ModelRequest:
    defaults: dict[str, Any] = dict(
        provider="openai",
        model="gpt-4o-mini",
        prompt="Hello.",
        temperature=0.0,
        max_tokens=128,
        seed=42,
        timeout_seconds=30,
    )
    defaults.update(overrides)
    return ModelRequest(**defaults)


def test_model_request_is_frozen() -> None:
    req = _req()
    with pytest.raises(FrozenInstanceError):
        req.prompt = "mutated"  # type: ignore[misc]


def test_execution_is_frozen() -> None:
    ex = Execution(
        request=_req(),
        output_text="Hi.",
        latency_ms=12.0,
        prompt_tokens=2,
        completion_tokens=1,
        cached=False,
        seed_provided=True,
    )
    with pytest.raises(FrozenInstanceError):
        ex.output_text = "mutated"  # type: ignore[misc]


def test_cache_key_is_hex_sha256() -> None:
    key = _req().cache_key
    assert isinstance(key, str)
    assert len(key) == 64
    int(key, 16)  # raises ValueError if not hex


def test_cache_key_is_deterministic() -> None:
    assert _req().cache_key == _req().cache_key


def test_cache_key_differs_when_prompt_changes() -> None:
    assert _req(prompt="Hello.").cache_key != _req(prompt="Hi.").cache_key


def test_cache_key_differs_when_model_changes() -> None:
    assert _req(model="gpt-4o-mini").cache_key != _req(model="gpt-4o").cache_key


def test_cache_key_differs_when_provider_changes() -> None:
    assert _req(provider="openai").cache_key != _req(provider="anthropic").cache_key


def test_cache_key_differs_when_max_tokens_changes() -> None:
    assert _req(max_tokens=128).cache_key != _req(max_tokens=256).cache_key


def test_cache_key_ignores_temperature_and_seed() -> None:
    """Engine gates cache lookup on temp==0, so temp+seed are not part of the key."""
    a = _req(temperature=0.0, seed=None).cache_key
    b = _req(temperature=0.5, seed=999).cache_key
    assert a == b
