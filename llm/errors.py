"""Provider-seam exceptions.

These are llm-layer errors raised by the provider clients. They deliberately do
NOT import the API taxonomy (api.errors): the dependency direction is api -> llm,
not the reverse. The pipeline / API layer catches these and maps them to the
ErrorCode taxonomy, so the seam stays import-safe and provider-agnostic.
"""

from __future__ import annotations


class ProviderError(Exception):
    """A provider call failed. Base for the more specific provider failures."""

    def __init__(self, *, provider: str, detail: str = "") -> None:
        super().__init__(detail or provider)
        self.provider = provider
        self.detail = detail


class ProviderTimeout(ProviderError):
    """The provider call timed out (maps to provider_timeout / 504)."""


class ProviderRefusal(ProviderError):
    """The model refused to answer (a refusal content part was returned)."""

    def __init__(self, *, provider: str, reason: str) -> None:
        super().__init__(provider=provider, detail=f"model refused: {reason}")
        self.reason = reason


class ProviderTruncation(ProviderError):
    """Output was truncated before completion (e.g. max_output_tokens)."""

    def __init__(self, *, provider: str, reason: str) -> None:
        super().__init__(provider=provider, detail=f"output truncated: {reason}")
        self.reason = reason
