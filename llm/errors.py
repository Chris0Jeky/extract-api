"""Provider-seam exceptions.

These are llm-layer errors raised by the provider clients. They deliberately do
NOT import the API taxonomy (api.errors): the dependency direction is api -> llm,
not the reverse. The pipeline / API layer catches these and maps them to the
ErrorCode taxonomy, so the seam stays import-safe and provider-agnostic.
"""

from __future__ import annotations


class ProviderError(Exception):
    """A provider call failed. Base for the more specific provider failures."""

    def __init__(self, *, provider: str, detail: str = "", cost_usd: float = 0.0) -> None:
        super().__init__(detail or provider)
        self.provider = provider
        self.detail = detail
        # Billed spend to reconcile into the budget guard: the failed call's OWN cost when
        # the provider returned a billable response (a refusal or a truncation still bills
        # output tokens) plus any prior-attempt spend the pipeline adds. 0.0 only when the
        # cost is genuinely unknown, e.g. a timeout or SDK error raised before any response.
        self.cost_usd = cost_usd


class ProviderTimeout(ProviderError):
    """The provider call timed out (maps to provider_timeout / 504)."""


class ProviderRefusal(ProviderError):
    """The model refused to answer (a refusal content part was returned)."""

    def __init__(self, *, provider: str, reason: str, cost_usd: float = 0.0) -> None:
        # A refusal is a completed, billed response, so carry its own cost (the client
        # reads usage before raising) so the budget guard does not under-count it.
        super().__init__(provider=provider, detail=f"model refused: {reason}", cost_usd=cost_usd)
        self.reason = reason


class ProviderTruncation(ProviderError):
    """Output was truncated before completion (e.g. max_output_tokens)."""

    def __init__(self, *, provider: str, reason: str, cost_usd: float = 0.0) -> None:
        # Truncation bills the generated output tokens (up to the cap), so carry the call's
        # own cost; otherwise the most expensive failure mode would escape the budget guard.
        super().__init__(provider=provider, detail=f"output truncated: {reason}", cost_usd=cost_usd)
        self.reason = reason
