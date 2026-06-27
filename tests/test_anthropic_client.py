"""AnthropicClient behavior against a mocked SDK: completion, refusal, truncation, errors.

No network and no API key: anthropic.Anthropic is monkeypatched to a fake whose
messages.create returns a canned Message-like object (or raises an SDK error). The
ANTHROPIC_PRICE_* env is provided by the autouse fixture in conftest.
"""

import types

import anthropic
import httpx
import pytest

from llm.client import AnthropicClient
from llm.errors import ProviderError, ProviderRefusal, ProviderTimeout, ProviderTruncation

SCHEMA = {"type": "object", "properties": {}, "required": []}


def _usage(tokens_in, tokens_out):
    return types.SimpleNamespace(input_tokens=tokens_in, output_tokens=tokens_out)


def _text_block(text):
    return types.SimpleNamespace(type="text", text=text)


def _message(*, text='{"ok": true}', stop_reason="end_turn", content=None, model="claude-x"):
    return types.SimpleNamespace(
        content=content if content is not None else [_text_block(text)],
        stop_reason=stop_reason,
        usage=_usage(100, 50),
        model=model,
    )


def _install(monkeypatch, *, message=None, raises=None, factory_raises=None):
    """Install a fake anthropic.Anthropic; return (construct kwargs, create kwargs) dicts."""
    captured: dict[str, object] = {}
    captured_call: dict[str, object] = {}

    def create(**kwargs):
        captured_call.update(kwargs)
        if raises is not None:
            raise raises
        return message

    def factory(**kwargs):
        captured.update(kwargs)
        if factory_raises is not None:
            raise factory_raises
        return types.SimpleNamespace(messages=types.SimpleNamespace(create=create))

    monkeypatch.setattr(anthropic, "Anthropic", factory)
    return captured, captured_call


def test_complete_returns_result(monkeypatch):
    _install(monkeypatch, message=_message())
    monkeypatch.setenv("ANTHROPIC_PRICE_IN_PER_M", "3.0")
    monkeypatch.setenv("ANTHROPIC_PRICE_OUT_PER_M", "15.0")
    result = AnthropicClient().complete(system="s", prompt="p", json_schema=SCHEMA)
    assert result.text == '{"ok": true}'
    assert result.tokens_in == 100
    assert result.tokens_out == 50
    assert result.cost_usd == pytest.approx((100 * 3.0 + 50 * 15.0) / 1_000_000)
    assert result.latency_ms >= 0.0
    assert result.stop_reason == "end_turn"
    assert result.model == "claude-x"


def test_max_tokens_raises_truncation(monkeypatch):
    _install(monkeypatch, message=_message(stop_reason="max_tokens"))
    with pytest.raises(ProviderTruncation):
        AnthropicClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_pause_turn_raises_truncation(monkeypatch):
    # A paused turn is incomplete; the synchronous single-shot seam cannot continue it.
    _install(monkeypatch, message=_message(stop_reason="pause_turn"))
    with pytest.raises(ProviderTruncation):
        AnthropicClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_refusal_raises(monkeypatch):
    _install(monkeypatch, message=_message(stop_reason="refusal", text=""))
    with pytest.raises(ProviderRefusal):
        AnthropicClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_timeout_raises(monkeypatch):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    _install(monkeypatch, raises=anthropic.APITimeoutError(request=req))
    with pytest.raises(ProviderTimeout):
        AnthropicClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_api_error_raises(monkeypatch):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    _install(monkeypatch, raises=anthropic.APIError("boom", req, body=None))
    with pytest.raises(ProviderError):
        AnthropicClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_construction_error_maps_to_provider_error(monkeypatch):
    # A base AnthropicError on construction (e.g. missing key) maps to ProviderError.
    _install(monkeypatch, factory_raises=anthropic.AnthropicError("api_key must be set"))
    with pytest.raises(ProviderError):
        AnthropicClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_empty_completion_raises(monkeypatch):
    # No text content blocks -> empty -> fail loud, not an empty-but-valid extraction.
    _install(monkeypatch, message=_message(content=[]))
    with pytest.raises(ProviderError):
        AnthropicClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_blank_text_raises(monkeypatch):
    _install(monkeypatch, message=_message(text="   "))
    with pytest.raises(ProviderError):
        AnthropicClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_text_concatenates_text_blocks_and_skips_others(monkeypatch):
    content = [
        _text_block('{"a":'),
        types.SimpleNamespace(type="thinking", thinking="ignored"),
        _text_block(" 1}"),
    ]
    _install(monkeypatch, message=_message(content=content))
    result = AnthropicClient().complete(system="s", prompt="p", json_schema=SCHEMA)
    assert result.text == '{"a": 1}'


def test_usage_none_yields_zero_cost(monkeypatch):
    message = _message()
    message.usage = None
    _install(monkeypatch, message=message)
    result = AnthropicClient().complete(system="s", prompt="p", json_schema=SCHEMA)
    assert result.tokens_in == 0
    assert result.tokens_out == 0
    assert result.cost_usd == 0.0


def test_model_missing_falls_back_to_configured(monkeypatch):
    message = _message()
    message.model = None
    _install(monkeypatch, message=message)
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-configured")
    result = AnthropicClient().complete(system="s", prompt="p", json_schema=SCHEMA)
    assert result.model == "claude-configured"


def test_request_timeout_and_retries_are_wired(monkeypatch):
    captured, _ = _install(monkeypatch, message=_message())
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_S", "12.5")
    monkeypatch.setenv("LLM_MAX_RETRIES", "1")
    AnthropicClient().complete(system="s", prompt="p", json_schema=SCHEMA)
    assert captured["timeout"] == 12.5
    assert captured["max_retries"] == 1


def test_missing_price_env_fails_loud(monkeypatch):
    # Prices are required and explicit (no silent default that mis-bills other models).
    monkeypatch.delenv("ANTHROPIC_PRICE_IN_PER_M", raising=False)
    monkeypatch.delenv("ANTHROPIC_PRICE_OUT_PER_M", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_PRICE"):
        AnthropicClient()


def test_gateway_bypass_uses_direct_anthropic_credentials(monkeypatch):
    captured, _ = _install(monkeypatch, message=_message())
    monkeypatch.setenv("GATEWAY_BYPASS", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "direct-anthropic-key")
    monkeypatch.setenv("LLM_API_KEY", "gateway-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://gateway.example")
    AnthropicClient().complete(system="s", prompt="p", json_schema=SCHEMA)
    assert captured["api_key"] == "direct-anthropic-key"  # not the gateway key
    assert captured["base_url"] is None  # direct to Anthropic, not the gateway URL


def test_output_config_carries_sanitized_json_schema(monkeypatch):
    # The schema is passed under output_config.format as a json_schema, and sanitized
    # (unsupported keywords like "format" are stripped) before it reaches the provider.
    _, call = _install(monkeypatch, message=_message())
    schema = {
        "type": "object",
        "properties": {"d": {"type": "string", "format": "date"}},
        "required": ["d"],
    }
    AnthropicClient().complete(system="sys", prompt="prm", json_schema=schema)
    output_config = call["output_config"]
    assert output_config["format"]["type"] == "json_schema"
    assert "format" not in output_config["format"]["schema"]["properties"]["d"]
    assert call["system"] == "sys"
    assert call["messages"] == [{"role": "user", "content": "prm"}]
    assert call["max_tokens"] == 4096
