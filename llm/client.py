"""The one provider seam. NO other module may import a provider SDK.

Routing is env-only. The seam reads LLM_PROVIDER_MODE (the fixture short-circuit) and
LLM_DEFAULT_PROVIDER (default resolution). OpenAIClient (T02) routes via LLM_BASE_URL +
LLM_API_KEY, except under GATEWAY_BYPASS=1, where it talks to OpenAI directly with
OPENAI_API_KEY and no gateway base URL. The Anthropic real-call path lands in T09.
Keeping it all env-driven means the week-10 gateway migration stays an env change,
not a code change. Provider SDKs are imported lazily inside complete() so importing
this module never needs credentials. cost_usd is carried on every result from day
one (ADR 0002).

Real call paths land in T02 (OpenAI responses.parse) and T09 (Anthropic
messages.parse); the FixtureClient (T04b) gives an offline deterministic path for
`make smoke` and tests.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from llm.errors import ProviderError, ProviderRefusal, ProviderTimeout, ProviderTruncation
from llm.schema_utils import sanitize_for_provider

if TYPE_CHECKING:
    from openai.types.responses import ResponseTextConfigParam


@dataclass(frozen=True)
class CompletionResult:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: float
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


def _float_env(name: str, default: str) -> float:
    raw = os.environ.get(name, default)
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"env {name}={raw!r} is not a valid float") from exc


def _float_env_required(name: str) -> float:
    raw = os.environ.get(name)
    if not raw:
        raise ValueError(f"env {name} is required: set the per-model price explicitly")
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"env {name}={raw!r} is not a valid float") from exc


def _int_env(name: str, default: str) -> int:
    raw = os.environ.get(name, default)
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"env {name}={raw!r} is not a valid int") from exc


def _first_refusal(response: object) -> str | None:
    """Return the first refusal string in the response output, or None.

    A refusal is a content part of type "refusal" on an output message; scanning
    defensively (getattr) keeps this robust to SDK shape drift.
    """
    for item in getattr(response, "output", None) or []:
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "refusal":
                return str(getattr(part, "refusal", "") or "")
    return None


class OpenAIClient:
    """OpenAI structured-output client (Responses API with strict json_schema).

    Returns raw JSON text (ADR 0002): the seam is text-based and the validation-retry
    loop re-validates. cost_usd uses env-configured per-million-token prices so there
    is no committed price table to drift; a gateway may later supply cost directly.
    """

    provider = "openai"

    def __init__(self) -> None:
        # GATEWAY_BYPASS=1: talk to OpenAI directly with the provider-specific key and
        # no gateway base URL. Otherwise route through the gateway's LLM_* config so the
        # week-10 migration is an env flip. (.env.example documents OPENAI_API_KEY as the
        # direct, not-through-the-gateway credential.)
        if os.environ.get("GATEWAY_BYPASS") == "1":
            self.base_url = None
            self.api_key = _env("OPENAI_API_KEY") or _env("LLM_API_KEY")
        else:
            self.base_url = _env("LLM_BASE_URL")
            self.api_key = _env("LLM_API_KEY")
        self.model = os.environ.get("OPENAI_MODEL", "")
        # Per-million-token prices (USD). REQUIRED and explicit: defaulting would bill
        # every model at one model's rate, silently producing wrong cost_usd. The
        # operator must set the prices for their OPENAI_MODEL. Fails loud if unset.
        self.price_in_per_m = _float_env_required("OPENAI_PRICE_IN_PER_M")
        self.price_out_per_m = _float_env_required("OPENAI_PRICE_OUT_PER_M")
        # Bound the synchronous call so a slow provider cannot pin a worker for the
        # SDK default (~600s). max_retries bounds the multiplier on transient errors.
        self.timeout_s = _float_env("LLM_REQUEST_TIMEOUT_S", "60")
        self.max_retries = _int_env("LLM_MAX_RETRIES", "2")

    def complete(
        self,
        *,
        system: str,
        prompt: str,
        json_schema: dict[str, object],
        max_tokens: int = 4096,
    ) -> CompletionResult:
        # Lazy, and the ONLY place a provider SDK is imported (gateway-seam rule).
        import openai
        from openai import OpenAI

        text_format = {
            "format": {
                "type": "json_schema",
                "name": "extraction",
                "schema": sanitize_for_provider(json_schema),
                "strict": True,
            }
        }
        start = time.perf_counter()
        try:
            # Construction can also raise (e.g. a missing/invalid api_key -> OpenAIError),
            # so it is inside the try and mapped to the taxonomy like the call itself.
            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout_s,
                max_retries=self.max_retries,
            )
            response = client.responses.create(
                model=self.model,
                instructions=system,
                input=prompt,
                text=cast("ResponseTextConfigParam", text_format),
                max_output_tokens=max_tokens,
            )
        except openai.APITimeoutError as exc:
            raise ProviderTimeout(provider=self.provider, detail=str(exc)) from exc
        except openai.APIError as exc:
            raise ProviderError(provider=self.provider, detail=str(exc)) from exc
        except openai.OpenAIError as exc:
            # Base SDK error (e.g. construction/config failures) that is not an APIError.
            raise ProviderError(provider=self.provider, detail=str(exc)) from exc
        latency_ms = (time.perf_counter() - start) * 1000.0

        status = getattr(response, "status", None)
        # Fail loud on every non-success outcome, in order, so a provider fault is
        # never silently returned as an empty-but-valid extraction.
        refusal = _first_refusal(response)
        if refusal is not None:
            raise ProviderRefusal(provider=self.provider, reason=refusal)
        if status in {"failed", "cancelled"}:
            err = getattr(response, "error", None)
            detail = str(getattr(err, "message", None) or status)
            raise ProviderError(provider=self.provider, detail=f"response {status}: {detail}")
        if status == "incomplete":
            details = getattr(response, "incomplete_details", None)
            reason = str(getattr(details, "reason", None) or "unknown")
            if reason == "content_filter":
                raise ProviderRefusal(provider=self.provider, reason=reason)
            raise ProviderTruncation(provider=self.provider, reason=reason)

        text = str(getattr(response, "output_text", "") or "")
        if not text.strip():
            raise ProviderError(provider=self.provider, detail="empty completion (no output text)")

        usage = getattr(response, "usage", None)
        tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
        return CompletionResult(
            text=text,
            model=getattr(response, "model", None) or self.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=self._cost_usd(tokens_in, tokens_out),
            latency_ms=latency_ms,
            stop_reason=str(status or "completed"),
        )

    def _cost_usd(self, tokens_in: int, tokens_out: int) -> float:
        # usage absent -> 0 tokens -> 0.0 (documented fallback when a degraded gateway
        # omits usage). A real gateway-supplied cost override lands with the gateway work.
        return (tokens_in * self.price_in_per_m + tokens_out * self.price_out_per_m) / 1_000_000.0


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
    """Deterministic in-process client for offline smoke + tests (T04b).

    Returns canned JSON text (no network, no key, cost 0). The validation-retry pipeline
    validates it exactly as it would a real provider's output, so `make smoke` and the
    endpoint tests exercise the full path offline. The canned text comes from the caller
    (FIXTURE_CANNED_TEXT, read in get_client). An empty canned text is a misconfiguration
    and fails loud rather than masquerading as an empty-but-valid extraction.
    """

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
        if not self._canned_text.strip():
            raise ProviderError(
                provider=self.provider,
                detail="FixtureClient has no canned text (set FIXTURE_CANNED_TEXT)",
            )
        return CompletionResult(
            text=self._canned_text,
            model=self.model,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            latency_ms=0.0,
            stop_reason="completed",
        )


def get_client(provider: str) -> LLMClient:
    """Resolve a provider client from env + the request's provider field."""
    if os.environ.get("LLM_PROVIDER_MODE") == "fixture":
        return FixtureClient(os.environ.get("FIXTURE_CANNED_TEXT", ""))
    resolved = provider
    if provider == "default":
        # M1 window: default to OpenAI, the only provider with a real call path. The
        # Anthropic path lands in T09; until then a bare "default" request must reach a
        # working provider, not the unimplemented stub. Override per deployment via env.
        resolved = os.environ.get("LLM_DEFAULT_PROVIDER", "openai")
    if resolved == "openai":
        return OpenAIClient()
    if resolved == "anthropic":
        return AnthropicClient()
    raise ValueError(f"unknown provider: {provider!r}")
