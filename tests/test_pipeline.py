"""Validation-retry pipeline: first-pass, fail-then-pass, both-fail, and error passthrough."""

import json
import logging

import pytest

from llm.client import CompletionResult
from llm.errors import ProviderTimeout
from llm.pipeline import ExtractionFailed, run_extraction
from schemas.invoice_v1 import InvoiceV1

_VALID = {
    "invoice_number": "INV-1",
    "issue_date": "2026-01-15",
    "due_date": None,
    "currency": "GBP",
    "subtotal_minor": 10000,
    "tax_minor": 2000,
    "total_minor": 12000,
    "vendor_name": "Acme Ltd",
    "vendor_tax_id": None,
    "buyer_name": None,
    "line_items": None,
}


def _json(**overrides):
    payload = dict(_VALID)
    payload.update(overrides)
    return json.dumps(payload)


VALID_JSON = _json()
# total != subtotal + tax -> the cross-field model validator raises ValidationError.
INVALID_JSON = _json(total_minor=99999)


class _ScriptedClient:
    """Plays a script of steps in order: a str step is returned as text, an Exception is raised."""

    provider = "fake"

    def __init__(self, steps):
        self._steps = list(steps)
        self.prompts: list[str] = []

    def complete(self, *, system, prompt, json_schema, max_tokens=4096):
        self.prompts.append(prompt)
        step = self._steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return CompletionResult(
            text=step,
            model="fake",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.0,
            latency_ms=0.0,
            stop_reason="completed",
        )


def test_first_pass_success():
    client = _ScriptedClient([VALID_JSON])
    model, result, attempts = run_extraction(client, InvoiceV1, system="sys", content="doc")
    assert isinstance(model, InvoiceV1)
    assert attempts == 1
    assert result.stop_reason == "completed"
    assert client.prompts == ["doc"]  # no feedback appended


def test_fail_then_pass_includes_previous_response_and_errors(caplog):
    client = _ScriptedClient([INVALID_JSON, VALID_JSON])
    with caplog.at_level(logging.WARNING, logger="extract.pipeline"):
        model, _result, attempts = run_extraction(client, InvoiceV1, system="sys", content="doc")
    assert isinstance(model, InvoiceV1)
    assert attempts == 2
    retry_prompt = client.prompts[1]
    assert "Your previous response was:" in retry_prompt
    assert INVALID_JSON in retry_prompt  # the model sees its own prior output
    assert "failed strict validation" in retry_prompt
    assert "kinds=" in caplog.text  # error categories logged
    assert "ValidationError" in caplog.text  # retry logged with its error class


def test_both_fail_raises_with_json_safe_trail():
    client = _ScriptedClient([INVALID_JSON, INVALID_JSON])
    with pytest.raises(ExtractionFailed) as excinfo:
        run_extraction(client, InvoiceV1, system="sys", content="doc")
    assert excinfo.value.attempts == 2
    assert len(excinfo.value.trail) == 2  # one error summary per attempt
    json.dumps(excinfo.value.trail)  # JSON-safe by construction; must not raise
    assert all(
        {"loc", "type", "msg"} <= set(err) for attempt in excinfo.value.trail for err in attempt
    )


def test_provider_error_on_first_attempt_propagates():
    client = _ScriptedClient([ProviderTimeout(provider="fake", detail="slow")])
    with pytest.raises(ProviderTimeout):
        run_extraction(client, InvoiceV1, system="sys", content="doc")


def test_provider_error_on_second_attempt_propagates():
    # A provider failure on the retry (after a first validation miss) must propagate too.
    client = _ScriptedClient([INVALID_JSON, ProviderTimeout(provider="fake", detail="slow")])
    with pytest.raises(ProviderTimeout):
        run_extraction(client, InvoiceV1, system="sys", content="doc")
