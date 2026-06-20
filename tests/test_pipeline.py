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
    """Returns canned completion texts in order, or raises a preset error."""

    provider = "fake"

    def __init__(self, texts=None, raises=None):
        self._texts = list(texts or [])
        self._raises = raises
        self.prompts: list[str] = []

    def complete(self, *, system, prompt, json_schema, max_tokens=4096):
        self.prompts.append(prompt)
        if self._raises is not None:
            raise self._raises
        return CompletionResult(
            text=self._texts.pop(0),
            model="fake",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.0,
            latency_ms=0.0,
            stop_reason="completed",
        )


def test_first_pass_success():
    client = _ScriptedClient(texts=[VALID_JSON])
    model, result, attempts = run_extraction(client, InvoiceV1, system="sys", content="doc")
    assert isinstance(model, InvoiceV1)
    assert attempts == 1
    assert result.stop_reason == "completed"
    assert client.prompts == ["doc"]  # no feedback appended


def test_fail_then_pass_appends_error_feedback(caplog):
    client = _ScriptedClient(texts=[INVALID_JSON, VALID_JSON])
    with caplog.at_level(logging.WARNING, logger="extract.pipeline"):
        model, _result, attempts = run_extraction(client, InvoiceV1, system="sys", content="doc")
    assert isinstance(model, InvoiceV1)
    assert attempts == 2
    # second attempt's prompt carries the failure list as feedback
    assert client.prompts[0] == "doc"
    assert "failed strict validation" in client.prompts[1]
    assert "ValidationError" in caplog.text  # retry logged with its error class


def test_both_fail_raises_with_full_trail():
    client = _ScriptedClient(texts=[INVALID_JSON, INVALID_JSON])
    with pytest.raises(ExtractionFailed) as excinfo:
        run_extraction(client, InvoiceV1, system="sys", content="doc")
    assert excinfo.value.attempts == 2
    assert len(excinfo.value.trail) == 2  # one error list per attempt


def test_provider_error_propagates_unchanged():
    client = _ScriptedClient(raises=ProviderTimeout(provider="fake", detail="slow"))
    with pytest.raises(ProviderTimeout):
        run_extraction(client, InvoiceV1, system="sys", content="doc")
