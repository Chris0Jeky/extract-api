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


def _response(*, text='{"ok": true}', status="completed", incomplete_reason=None, output=None):
    details = types.SimpleNamespace(reason=incomplete_reason) if incomplete_reason else None
    return types.SimpleNamespace(
        output_text=text,
        status=status,
        incomplete_details=details,
        usage=_usage(100, 50),
        output=output or [],
        model="gpt-4o-mini",
    )


def _install(monkeypatch, *, response=None, raises=None):
    def create(**kwargs):
        if raises is not None:
            raise raises
        return response

    fake_client = types.SimpleNamespace(responses=types.SimpleNamespace(create=create))
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: fake_client)


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
