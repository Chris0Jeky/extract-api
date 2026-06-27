"""Provider seam: env-only routing. Per-provider call behavior lives in
test_openai_client.py and test_anthropic_client.py."""

import pytest

from llm.client import AnthropicClient, FixtureClient, OpenAIClient, get_client
from llm.errors import ProviderError


def test_get_client_routes_explicit_providers(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    assert isinstance(get_client("openai"), OpenAIClient)
    assert isinstance(get_client("anthropic"), AnthropicClient)


def test_get_client_default_uses_env(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    monkeypatch.setenv("LLM_DEFAULT_PROVIDER", "anthropic")
    assert isinstance(get_client("default"), AnthropicClient)


def test_get_client_default_falls_back_to_openai(monkeypatch):
    # M1 window: with no LLM_DEFAULT_PROVIDER set, "default" resolves to the only
    # implemented real provider (OpenAI), not the Anthropic stub.
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    monkeypatch.delenv("LLM_DEFAULT_PROVIDER", raising=False)
    assert isinstance(get_client("default"), OpenAIClient)


def test_get_client_empty_default_env_falls_back_to_openai(monkeypatch):
    # An empty LLM_DEFAULT_PROVIDER= must also fall back to openai, not resolve to "" ->
    # unknown provider (os.environ.get default would not catch the empty-string case).
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    monkeypatch.setenv("LLM_DEFAULT_PROVIDER", "")
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
