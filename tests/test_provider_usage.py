"""Malformed provider metadata must not corrupt spend or escape the provider taxonomy."""

import types
from contextlib import nullcontext

import anthropic
import openai
import pytest

from llm.client import AnthropicClient, OpenAIClient
from llm.errors import ProviderError

SCHEMA = {"type": "object", "properties": {}, "required": []}


@pytest.fixture(params=["openai", "anthropic"])
def provider_response(request, monkeypatch):
    response = types.SimpleNamespace(
        output_text='{"ok": true}',
        output=[],
        content=[types.SimpleNamespace(type="text", text='{"ok": true}')],
        status="completed",
        stop_reason="end_turn",
        usage=types.SimpleNamespace(input_tokens=100, output_tokens=50),
        model="test-model",
    )
    endpoint = types.SimpleNamespace(create=lambda **kwargs: response)
    if request.param == "openai":
        monkeypatch.setattr(
            openai,
            "OpenAI",
            lambda **kwargs: nullcontext(types.SimpleNamespace(responses=endpoint)),
        )
        client = OpenAIClient()
    else:
        monkeypatch.setattr(
            anthropic,
            "Anthropic",
            lambda **kwargs: nullcontext(types.SimpleNamespace(messages=endpoint)),
        )
        client = AnthropicClient()
    return client, response


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
@pytest.mark.parametrize("bad", [-1, True, "12", 1.5, float("nan"), float("inf"), "private-data"])
def test_invalid_usage_is_a_provider_error(provider_response, field, bad):
    client, response = provider_response
    setattr(response.usage, field, bad)
    with pytest.raises(ProviderError) as excinfo:
        client.complete(system="s", prompt="p", json_schema=SCHEMA)
    assert excinfo.value.provider == client.provider
    assert excinfo.value.cost_usd == 0.0  # malformed usage cannot establish this call's cost
    assert field in str(excinfo.value)
    assert "private-data" not in str(excinfo.value)


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
def test_missing_usage_count_preserves_zero_fallback(provider_response, field):
    client, response = provider_response
    setattr(response.usage, field, None)
    result = client.complete(system="s", prompt="p", json_schema=SCHEMA)
    assert (result.tokens_in if field == "input_tokens" else result.tokens_out) == 0
    assert result.cost_usd >= 0.0


@pytest.mark.parametrize("overflow", ["float", "integer"])
def test_unrepresentable_usage_cost_is_a_provider_error(provider_response, overflow):
    client, response = provider_response
    if overflow == "float":
        client.price_in_per_m = 1e308  # finite configuration, non-finite product
    else:
        response.usage.input_tokens = 10**400
    with pytest.raises(ProviderError, match="cost") as excinfo:
        client.complete(system="s", prompt="p", json_schema=SCHEMA)
    assert excinfo.value.cost_usd == 0.0
