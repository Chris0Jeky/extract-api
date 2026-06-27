"""OpenAIClient behavior against a mocked SDK: completion, refusal, truncation, errors.

No network and no API key: openai.OpenAI is monkeypatched to a fake whose
responses.create returns a canned response object (or raises an SDK error).
"""

import types

import httpx
import openai
import pytest

from llm.client import OpenAIClient
from llm.errors import ProviderError, ProviderRefusal, ProviderTimeout, ProviderTruncation

SCHEMA = {"type": "object", "properties": {}, "required": []}


def _usage(tokens_in, tokens_out):
    return types.SimpleNamespace(
        input_tokens=tokens_in, output_tokens=tokens_out, total_tokens=tokens_in + tokens_out
    )


def _response(
    *, text='{"ok": true}', status="completed", incomplete_reason=None, output=None, error=None
):
    details = types.SimpleNamespace(reason=incomplete_reason) if incomplete_reason else None
    return types.SimpleNamespace(
        output_text=text,
        status=status,
        incomplete_details=details,
        usage=_usage(100, 50),
        output=output or [],
        model="gpt-4o-mini",
        error=error,
    )


def _install(monkeypatch, *, response=None, raises=None):
    """Install a fake openai.OpenAI; return a dict of the kwargs it was constructed with."""
    captured: dict[str, object] = {}

    def create(**kwargs):
        if raises is not None:
            raise raises
        return response

    def factory(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(responses=types.SimpleNamespace(create=create))

    monkeypatch.setattr(openai, "OpenAI", factory)
    return captured


def test_complete_returns_result(monkeypatch):
    _install(monkeypatch, response=_response())
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_PRICE_IN_PER_M", "1.0")
    monkeypatch.setenv("OPENAI_PRICE_OUT_PER_M", "2.0")
    result = OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)
    assert result.text == '{"ok": true}'
    assert result.tokens_in == 100
    assert result.tokens_out == 50
    assert result.cost_usd == pytest.approx((100 * 1.0 + 50 * 2.0) / 1_000_000)
    assert result.latency_ms >= 0.0
    assert result.stop_reason == "completed"
    assert result.model == "gpt-4o-mini"


def test_truncation_raises(monkeypatch):
    _install(
        monkeypatch,
        response=_response(status="incomplete", incomplete_reason="max_output_tokens", text=""),
    )
    with pytest.raises(ProviderTruncation):
        OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_refusal_raises(monkeypatch):
    refusal_part = types.SimpleNamespace(type="refusal", refusal="cannot help")
    message = types.SimpleNamespace(content=[refusal_part])
    _install(monkeypatch, response=_response(output=[message]))
    with pytest.raises(ProviderRefusal):
        OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_truncation_carries_billed_cost(monkeypatch):
    # A truncation is a completed, billed response, so the call's own cost must ride on the
    # exception (else the budget guard under-counts the most expensive failure mode).
    monkeypatch.setenv("OPENAI_PRICE_IN_PER_M", "1.0")
    monkeypatch.setenv("OPENAI_PRICE_OUT_PER_M", "2.0")
    _install(
        monkeypatch,
        response=_response(status="incomplete", incomplete_reason="max_output_tokens", text=""),
    )
    with pytest.raises(ProviderTruncation) as excinfo:
        OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)
    assert excinfo.value.cost_usd == pytest.approx((100 * 1.0 + 50 * 2.0) / 1_000_000)


def test_refusal_carries_billed_cost(monkeypatch):
    # A refusal is also a billed response; its cost must ride on the exception too.
    monkeypatch.setenv("OPENAI_PRICE_IN_PER_M", "1.0")
    monkeypatch.setenv("OPENAI_PRICE_OUT_PER_M", "2.0")
    refusal_part = types.SimpleNamespace(type="refusal", refusal="cannot help")
    message = types.SimpleNamespace(content=[refusal_part])
    _install(monkeypatch, response=_response(output=[message]))
    with pytest.raises(ProviderRefusal) as excinfo:
        OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)
    assert excinfo.value.cost_usd == pytest.approx((100 * 1.0 + 50 * 2.0) / 1_000_000)


def test_timeout_raises(monkeypatch):
    req = httpx.Request("POST", "https://api.openai.com/v1/responses")
    _install(monkeypatch, raises=openai.APITimeoutError(request=req))
    with pytest.raises(ProviderTimeout):
        OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_api_error_raises(monkeypatch):
    req = httpx.Request("POST", "https://api.openai.com/v1/responses")
    _install(monkeypatch, raises=openai.APIError("boom", req, body=None))
    with pytest.raises(ProviderError):
        OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_failed_status_raises_provider_error(monkeypatch):
    err = types.SimpleNamespace(code="server_error", message="upstream boom")
    _install(monkeypatch, response=_response(status="failed", text="", output=[], error=err))
    with pytest.raises(ProviderError) as excinfo:
        OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)
    assert "upstream boom" in str(excinfo.value)


def test_content_filter_incomplete_raises_refusal(monkeypatch):
    # An incomplete response stopped by the content filter is a refusal, not truncation.
    _install(
        monkeypatch,
        response=_response(status="incomplete", incomplete_reason="content_filter", text=""),
    )
    with pytest.raises(ProviderRefusal):
        OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_empty_completion_raises_provider_error(monkeypatch):
    _install(monkeypatch, response=_response(status="completed", text=""))
    with pytest.raises(ProviderError):
        OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_usage_none_yields_zero_cost(monkeypatch):
    response = _response()
    response.usage = None
    _install(monkeypatch, response=response)
    result = OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)
    assert result.tokens_in == 0
    assert result.tokens_out == 0
    assert result.cost_usd == 0.0


def test_model_missing_falls_back_to_configured(monkeypatch):
    response = _response()
    response.model = None
    _install(monkeypatch, response=response)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-configured")
    result = OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)
    assert result.model == "gpt-configured"


def test_refusal_takes_precedence_over_incomplete(monkeypatch):
    refusal_part = types.SimpleNamespace(type="refusal", refusal="no")
    message = types.SimpleNamespace(content=[refusal_part])
    _install(
        monkeypatch,
        response=_response(
            status="incomplete", incomplete_reason="max_output_tokens", output=[message], text=""
        ),
    )
    with pytest.raises(ProviderRefusal):
        OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_request_timeout_and_retries_are_wired(monkeypatch):
    captured = _install(monkeypatch, response=_response())
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_S", "12.5")
    monkeypatch.setenv("LLM_MAX_RETRIES", "1")
    OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)
    assert captured["timeout"] == 12.5
    assert captured["max_retries"] == 1


def test_missing_price_env_fails_loud(monkeypatch):
    # Prices are required and explicit (no silent default that mis-bills other models).
    monkeypatch.delenv("OPENAI_PRICE_IN_PER_M", raising=False)
    monkeypatch.delenv("OPENAI_PRICE_OUT_PER_M", raising=False)
    with pytest.raises(ValueError, match="OPENAI_PRICE"):
        OpenAIClient()


def test_sdk_construction_error_maps_to_provider_error(monkeypatch):
    def boom(**kwargs):
        raise openai.OpenAIError("the api_key client option must be set")

    monkeypatch.setattr(openai, "OpenAI", boom)
    with pytest.raises(ProviderError):
        OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)


def test_gateway_bypass_uses_direct_openai_credentials(monkeypatch):
    captured = _install(monkeypatch, response=_response())
    monkeypatch.setenv("GATEWAY_BYPASS", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "direct-openai-key")
    monkeypatch.setenv("LLM_API_KEY", "gateway-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://gateway.example")
    OpenAIClient().complete(system="s", prompt="p", json_schema=SCHEMA)
    assert captured["api_key"] == "direct-openai-key"  # not the gateway key
    assert captured["base_url"] is None  # direct to OpenAI, not the gateway URL
