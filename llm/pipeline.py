"""Validation-retry pipeline: provider call -> strict validate -> one feedback retry.

The providers' structured output guarantees SHAPE, not SEMANTICS (ADR 0002), so the
cross-field / normalization / value constraints that live in the Pydantic models are
enforced here, after parse. On the first ValidationError the model's previous response
and a JSON-safe error summary are appended to the prompt and the provider is asked once
more; a second failure raises ExtractionFailed carrying the full per-attempt trail (the
API layer maps it to 422 validation_failed). Provider-seam errors (llm.errors.*)
propagate unchanged.

Two attempts total (one feedback retry), matching the T03 definition of done and the
"attempt 2 appends the exact failure list; second failure returns 422" decision.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails

from llm.client import CompletionResult, LLMClient

logger = logging.getLogger("extract.pipeline")

# Attempt 1 (no feedback) + attempt 2 (previous response + failure list); a second
# failure is terminal. CLAUDE.md's "max 2 retries" header reads as 2 ATTEMPTS here,
# matching the T03 DoD and ADR 0002 ("retry attempt 2"); the wording reconciliation is
# an owner decision.
MAX_ATTEMPTS = 2

# A per-attempt list of summarized validation errors (location / kind / message).
ErrorSummary = list[dict[str, object]]


class ExtractionFailed(Exception):
    """Strict validation failed on every attempt; carries the per-attempt error trail.

    `trail` is JSON-safe by construction (loc/type/msg only), so the API layer can render
    the 422 body without re-serializing.
    """

    def __init__(self, *, attempts: int, trail: list[ErrorSummary]) -> None:
        super().__init__(f"extraction failed strict validation after {attempts} attempt(s)")
        self.attempts = attempts
        self.trail = trail


def _summarize(errors: list[ErrorDetails]) -> ErrorSummary:
    """JSON-safe, prompt-safe view of pydantic errors: location, kind, message.

    Drops the bulky/echoed `input` and `ctx` payloads (the model gets its previous
    response separately), which also keeps the result valid JSON: a model may emit a
    non-finite float that pydantic accepts, which would otherwise ride along in `input`
    as a bare NaN/Infinity token.
    """
    return [{"loc": list(e["loc"]), "type": e["type"], "msg": e["msg"]} for e in errors]


def _retry_prompt(content: str, previous_text: str, summary: ErrorSummary) -> str:
    return (
        content
        + "\n\nYour previous response was:\n"
        + previous_text
        + "\n\nIt failed strict validation with these errors (location / kind / message). "
        + "Fix them and return the complete, corrected object:\n"
        + json.dumps(summary, indent=2)
    )


def run_extraction(
    client: LLMClient,
    model_cls: type[BaseModel],
    *,
    system: str,
    content: str,
    max_tokens: int = 4096,
) -> tuple[BaseModel, CompletionResult, int]:
    """Call the provider, strict-validate, retry once with the previous response + errors.

    Returns (validated_model, last_result, attempts). Raises ExtractionFailed after
    MAX_ATTEMPTS validation failures; provider-seam errors (llm.errors.*) propagate.
    """
    schema = model_cls.model_json_schema()
    prompt = content
    trail: list[ErrorSummary] = []
    # Every attempt is a billed provider call, so cost/tokens/latency accumulate across
    # the loop; the returned result reflects the TOTAL spend, not just the last call.
    tokens_in = tokens_out = 0
    cost_usd = latency_ms = 0.0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result = client.complete(
            system=system, prompt=prompt, json_schema=schema, max_tokens=max_tokens
        )
        tokens_in += result.tokens_in
        tokens_out += result.tokens_out
        cost_usd += result.cost_usd
        latency_ms += result.latency_ms
        try:
            model = model_cls.model_validate_json(result.text)
        except ValidationError as exc:
            summary = _summarize(exc.errors())
            trail.append(summary)
            kinds = sorted({str(item["type"]) for item in summary})
            logger.warning(
                "extraction attempt %d/%d failed strict validation: %s kinds=%s (%d error(s))",
                attempt,
                MAX_ATTEMPTS,
                type(exc).__name__,
                kinds,
                len(summary),
            )
            prompt = _retry_prompt(content, result.text, summary)
            continue
        aggregated = CompletionResult(
            text=result.text,
            model=result.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            stop_reason=result.stop_reason,
        )
        return model, aggregated, attempt
    raise ExtractionFailed(attempts=len(trail), trail=trail)
