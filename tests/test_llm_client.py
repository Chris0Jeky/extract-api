"""Provider seam: env-only routing now; the real calls are stubs."""

import pytest

from llm.client import AnthropicClient, FixtureClient, OpenAIClient, get_client
from llm.errors import ProviderError


def test_get_client_routes_explicit_providers(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    assert isinstance(get_client("openai"), OpenAIClient)
    assert isinstance(get_client("anthropic"), AnthropicClient)


def test_get_client_default_uses_env(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    monkeypatch.setenv("LLM_DEFAULT_PROVIDER", "openai")
    assert isinstance(get_client("default"), OpenAIClient)


def test_get_client_fixture_mode_overrides(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_MODE", "fixture")
    assert isinstance(get_client("openai"), FixtureClient)


def test_get_client_fixture_mode_reads_canned_text(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_MODE", "fixture")
    monkeypatch.setenv("FIXTURE_CANNED_TEXT", '{"hello": "world"}')
    client = get_client("openai")
    assert isinstance(client, FixtureClient)
    result = client.complete(system="s", prompt="p", json_schema={})
    assert result.text == '{"hello": "world"}'


def test_get_client_unknown_provider_raises(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    with pytest.raises(ValueError, match="unknown provider"):
        get_client("telepathy")


def test_fixture_client_returns_canned_text_at_zero_cost():
    result = FixtureClient('{"ok": true}').complete(system="s", prompt="p", json_schema={})
    assert result.text == '{"ok": true}'
    assert result.cost_usd == 0.0
    assert result.stop_reason == "completed"
    assert result.model == "fixture"


def test_fixture_client_without_canned_text_fails_loud():
    # An unconfigured fixture client must not return an empty-but-valid extraction.
    with pytest.raises(ProviderError, match="canned text"):
        FixtureClient().complete(system="s", prompt="p", json_schema={})


def test_anthropic_path_is_stubbed():
    # OpenAI (T02) and FixtureClient (T04b) are implemented; Anthropic fails loud until T09.
    with pytest.raises(NotImplementedError):
        AnthropicClient().complete(system="s", prompt="p", json_schema={})
