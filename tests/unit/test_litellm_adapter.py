"""Tests for falsifyai.execution.litellm_adapter — mocked LiteLLM calls only."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from falsifyai.execution.errors import ExecutionError
from falsifyai.execution.litellm_adapter import LiteLLMAdapter
from falsifyai.execution.models import ModelRequest


def _req(**overrides: Any) -> ModelRequest:
    defaults: dict[str, Any] = dict(
        provider="openai",
        model="gpt-4o-mini",
        prompt="Hello.",
        temperature=0.0,
        max_tokens=128,
        seed=None,
        timeout_seconds=30,
    )
    defaults.update(overrides)
    return ModelRequest(**defaults)


def _mock_response(
    content: str = "Hi.",
    prompt_tokens: int = 2,
    completion_tokens: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


@patch("falsifyai.execution.litellm_adapter.litellm")
def test_request_is_mapped_to_litellm_kwargs(mock_litellm: Any) -> None:
    mock_litellm.completion.return_value = _mock_response()
    adapter = LiteLLMAdapter()
    adapter.execute(_req(seed=42, temperature=0.3, max_tokens=256, timeout_seconds=60))

    _, kwargs = mock_litellm.completion.call_args
    assert kwargs["model"] == "openai/gpt-4o-mini"
    assert kwargs["messages"] == [{"role": "user", "content": "Hello."}]
    assert kwargs["temperature"] == 0.3
    assert kwargs["max_tokens"] == 256
    assert kwargs["timeout"] == 60
    assert kwargs["seed"] == 42


@patch("falsifyai.execution.litellm_adapter.litellm")
def test_seed_omitted_when_none(mock_litellm: Any) -> None:
    mock_litellm.completion.return_value = _mock_response()
    adapter = LiteLLMAdapter()
    adapter.execute(_req(seed=None))
    _, kwargs = mock_litellm.completion.call_args
    assert "seed" not in kwargs


@patch("falsifyai.execution.litellm_adapter.litellm")
def test_response_is_mapped_to_execution(mock_litellm: Any) -> None:
    mock_litellm.completion.return_value = _mock_response(
        content="Paris.", prompt_tokens=10, completion_tokens=1
    )
    adapter = LiteLLMAdapter()
    execution = adapter.execute(_req())
    assert execution.output_text == "Paris."
    assert execution.prompt_tokens == 10
    assert execution.completion_tokens == 1
    assert execution.cached is False
    assert execution.latency_ms >= 0.0


@patch("falsifyai.execution.litellm_adapter.litellm")
def test_seed_provided_flag_reflects_request(mock_litellm: Any) -> None:
    mock_litellm.completion.return_value = _mock_response()
    adapter = LiteLLMAdapter()
    with_seed = adapter.execute(_req(seed=42))
    no_seed = adapter.execute(_req(seed=None))
    assert with_seed.seed_provided is True
    assert no_seed.seed_provided is False


@patch("falsifyai.execution.litellm_adapter.litellm")
def test_completion_exception_wraps_as_execution_error(mock_litellm: Any) -> None:
    mock_litellm.completion.side_effect = RuntimeError("boom")
    adapter = LiteLLMAdapter()
    with pytest.raises(ExecutionError) as exc_info:
        adapter.execute(_req())
    assert "boom" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, RuntimeError)


@patch("falsifyai.execution.litellm_adapter.litellm")
def test_malformed_response_wraps_as_execution_error(mock_litellm: Any) -> None:
    mock_litellm.completion.return_value = SimpleNamespace(choices=[])
    adapter = LiteLLMAdapter()
    with pytest.raises(ExecutionError):
        adapter.execute(_req())


@patch("falsifyai.execution.litellm_adapter.litellm")
def test_missing_usage_yields_none_token_counts(mock_litellm: Any) -> None:
    """Some providers do not report token usage; that must not crash."""
    mock_litellm.completion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    )
    adapter = LiteLLMAdapter()
    execution = adapter.execute(_req())
    assert execution.prompt_tokens is None
    assert execution.completion_tokens is None


@patch("falsifyai.execution.litellm_adapter.litellm")
def test_none_content_becomes_empty_string(mock_litellm: Any) -> None:
    """LiteLLM occasionally returns content=None; we coerce to empty string."""
    mock_litellm.completion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
    )
    adapter = LiteLLMAdapter()
    execution = adapter.execute(_req())
    assert execution.output_text == ""
