"""The one provider seam. NO other module may import a provider SDK.

Routing is env-only (LLM_BASE_URL, LLM_API_KEY, GATEWAY_BYPASS, LLM_PROVIDER_MODE)
so the week-10 gateway migration is an env change, not a code change. Provider
SDKs are imported lazily inside complete() so importing this module never needs
credentials. cost_usd is carried on every result from day one (ADR 0002).

Real call paths land in T02 (OpenAI responses.parse) and T09 (Anthropic
messages.parse); the FixtureClient (T04b) gives an offline deterministic path for
`make smoke` and tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CompletionResult:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    stop_reason: str


class LLMClient(Protocol):
    provider: str

    def complete(
        self,
        *,
        system: str,
        prompt: str,
        json_schema: dict[str, object],
        max_tokens: int = 4096,
    ) -> CompletionResult: ...


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    return value or None


class OpenAIClient:
    """OpenAI structured-output client. Real call lands in T02."""

    provider = "openai"

    def __init__(self) -> None:
        self.base_url = _env("LLM_BASE_URL")
        self.api_key = _env("LLM_API_KEY")
        self.model = os.environ.get("OPENAI_MODEL", "")

    def complete(
        self,
        *,
        system: str,
        prompt: str,
        json_schema: dict[str, object],
        max_tokens: int = 4096,
    ) -> CompletionResult:
        # from openai import OpenAI  # lazy import lands with the real call (T02)
        raise NotImplementedError("OpenAI responses.parse path lands in T02")


class AnthropicClient:
    """Anthropic structured-output client. Real call lands in T09."""

    provider = "anthropic"

    def __init__(self) -> None:
        self.base_url = _env("LLM_BASE_URL")
        self.api_key = _env("LLM_API_KEY")
        self.model = os.environ.get("ANTHROPIC_MODEL", "")

    def complete(
        self,
        *,
        system: str,
        prompt: str,
        json_schema: dict[str, object],
        max_tokens: int = 4096,
    ) -> CompletionResult:
        # from anthropic import Anthropic  # lazy import lands with the real call (T09)
        raise NotImplementedError("Anthropic messages.parse path lands in T09")


class FixtureClient:
    """Deterministic in-process client for offline smoke + tests (T04b)."""

    provider = "fixture"

    def __init__(self, canned_text: str = "") -> None:
        self.model = "fixture"
        self._canned_text = canned_text

    def complete(
        self,
        *,
        system: str,
        prompt: str,
        json_schema: dict[str, object],
        max_tokens: int = 4096,
    ) -> CompletionResult:
        raise NotImplementedError("fixture canned-output wiring lands in T04b")


def get_client(provider: str) -> LLMClient:
    """Resolve a provider client from env + the request's provider field."""
    if os.environ.get("LLM_PROVIDER_MODE") == "fixture":
        return FixtureClient()
    resolved = provider
    if provider == "default":
        resolved = os.environ.get("LLM_DEFAULT_PROVIDER", "anthropic")
    if resolved == "openai":
        return OpenAIClient()
    if resolved == "anthropic":
        return AnthropicClient()
    raise ValueError(f"unknown provider: {provider!r}")
