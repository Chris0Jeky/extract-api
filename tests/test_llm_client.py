"""Provider seam: env-only routing now; the real calls are stubs."""

import pytest

from llm.client import AnthropicClient, FixtureClient, OpenAIClient, get_client


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


def test_get_client_unknown_provider_raises(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    with pytest.raises(ValueError, match="unknown provider"):
        get_client("telepathy")


def test_complete_paths_are_stubbed():
    schema: dict[str, object] = {}
    for client in (OpenAIClient(), AnthropicClient(), FixtureClient()):
        with pytest.raises(NotImplementedError):
            client.complete(system="s", prompt="p", json_schema=schema)
