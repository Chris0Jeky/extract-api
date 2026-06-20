"""Validation-retry pipeline: provider call -> strict validate -> one feedback retry.

The providers' structured output guarantees SHAPE, not SEMANTICS (ADR 0002), so the
cross-field / normalization / value constraints that live in the Pydantic models are
enforced here, after parse. On the first ValidationError the exact error list is
appended to the prompt and the provider is asked once more; a second failure raises
ExtractionFailed carrying the full per-attempt trail (the API layer maps it to 422
validation_failed). Provider-seam errors (llm.errors.*) propagate unchanged.

Two attempts total (one feedback retry), matching the T03 definition of done and the
"attempt 2 appends the exact failure list; second failure returns 422" decision.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ValidationError

from llm.client import CompletionResult, LLMClient

logger = logging.getLogger("extract.pipeline")

# Attempt 1 (no feedback) + attempt 2 (failure list appended). A second failure is terminal.
MAX_ATTEMPTS = 2


class ExtractionFailed(Exception):
    """Strict validation failed on every attempt; carries the per-attempt error trail."""

    def __init__(self, *, attempts: int, trail: list[object]) -> None:
        super().__init__(f"extraction failed strict validation after {attempts} attempt(s)")
        self.attempts = attempts
        self.trail = trail


def _feedback_suffix(errors: object) -> str:
    # default=str keeps the dump JSON-safe: err.errors() can carry date/Decimal in `input`.
    return (
        "\n\nThe previous response failed strict validation with these errors. "
        "Fix them and return the complete object again:\n"
        + json.dumps(errors, indent=2, default=str)
    )


def run_extraction(
    client: LLMClient,
    model_cls: type[BaseModel],
    *,
    system: str,
    content: str,
    max_tokens: int = 4096,
) -> tuple[BaseModel, CompletionResult, int]:
    """Call the provider, strict-validate, retry once with the failure list.

    Returns (validated_model, last_result, attempts). Raises ExtractionFailed after
    MAX_ATTEMPTS validation failures; provider-seam errors (llm.errors.*) propagate.
    """
    schema = model_cls.model_json_schema()
    prompt = content
    trail: list[object] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result = client.complete(
            system=system, prompt=prompt, json_schema=schema, max_tokens=max_tokens
        )
        try:
            model = model_cls.model_validate_json(result.text)
        except ValidationError as exc:
            errors = exc.errors()
            trail.append(errors)
            logger.warning(
                "extraction attempt %d/%d failed strict validation: %s (%d error(s))",
                attempt,
                MAX_ATTEMPTS,
                type(exc).__name__,
                len(errors),
            )
            prompt = content + _feedback_suffix(errors)
            continue
        return model, result, attempt
    raise ExtractionFailed(attempts=MAX_ATTEMPTS, trail=trail)
