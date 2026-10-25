"""Validation-retry pipeline: first-pass, fail-then-pass, both-fail, and error passthrough."""

import json
import logging

import pytest

from llm.client import CompletionResult
from llm.errors import ProviderRefusal, ProviderTimeout, ProviderTruncation
from llm.pipeline import ExtractionFailed, run_extraction
from schemas.invoice_v1 import InvoiceV1
from schemas.job_posting_v1 import JobPostingV1

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

    def __init__(self, steps, cost_usd=0.0):
        self._steps = list(steps)
        self.prompts: list[str] = []
        self._cost_usd = cost_usd

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
            cost_usd=self._cost_usd,
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


@pytest.mark.parametrize("quantity", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_quantity_retries_and_preserves_error_trail(quantity):
    item = {
        "description": "Widget",
        "quantity": quantity,
        "unit_price_minor": 1,
        "amount_minor": 10000,
    }
    invalid = _json(line_items=[item])
    valid = _json(line_items=[dict(item, quantity=1.25)])
    client = _ScriptedClient([invalid, valid])
    model, _, attempts = run_extraction(client, InvoiceV1, system="sys", content="doc")
    assert attempts == 2
    assert model.model_dump(mode="json")["line_items"][0]["quantity"] == 1.25
    assert invalid in client.prompts[1]
    assert "finite_number" in client.prompts[1]

    client = _ScriptedClient([invalid, invalid], cost_usd=0.5)
    with pytest.raises(ExtractionFailed) as excinfo:
        run_extraction(client, InvoiceV1, system="sys", content="doc")
    failure = excinfo.value
    assert failure.attempts == 2
    assert failure.cost_usd == pytest.approx(1.0)
    assert len(failure.trail) == 2
    assert failure.trail[0] == failure.trail[1]
    for errors in failure.trail:
        assert any(
            err["type"] == "finite_number" and err["loc"][:3] == ["line_items", 0, "quantity"]
            for err in errors
        )
    assert json.loads(client.prompts[1].split("corrected object:\n", 1)[1]) == failure.trail[0]
    json.dumps(failure.trail, allow_nan=False)


@pytest.mark.parametrize(
    ("field", "value"),
    [("salary_min", -1), ("salary_max", -1), ("title", ""), ("company", " \t\n")],
)
def test_job_invalid_value_retries_with_exact_errors(field, value):
    valid = {
        "title": "Engineer",
        "company": None,
        "location": None,
        "remote_policy": "unspecified",
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "GBP",
        "salary_period": "unspecified",
        "employment_type": "unspecified",
        "seniority": "unspecified",
        "visa_sponsorship": "unspecified",
        "posted_date": None,
    }
    invalid = json.dumps(dict(valid, **{field: value}))
    client = _ScriptedClient([invalid, json.dumps(valid)])
    model, _, attempts = run_extraction(client, JobPostingV1, system="sys", content="doc")
    assert model.model_dump(mode="json") == valid
    assert attempts == 2
    assert invalid in client.prompts[1]
    assert field in client.prompts[1]

    client = _ScriptedClient([invalid, invalid])
    with pytest.raises(ExtractionFailed) as excinfo:
        run_extraction(client, JobPostingV1, system="sys", content="doc")
    assert excinfo.value.attempts == 2
    assert len(excinfo.value.trail) == 2
    assert excinfo.value.trail[0] == excinfo.value.trail[1]
    assert (
        json.loads(client.prompts[1].split("corrected object:\n", 1)[1]) == excinfo.value.trail[0]
    )
    assert all(field in err["msg"] or field in err["loc"] for err in excinfo.value.trail[0])


def test_fail_then_pass_includes_previous_response_and_errors(caplog):
    client = _ScriptedClient([INVALID_JSON, VALID_JSON])
    with caplog.at_level(logging.WARNING, logger="extract.pipeline"):
        model, result, attempts = run_extraction(client, InvoiceV1, system="sys", content="doc")
    assert isinstance(model, InvoiceV1)
    assert attempts == 2
    assert result.tokens_in == 2  # usage summed across both billed attempts (1 + 1)
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


def test_both_fail_carries_total_billed_cost():
    # ExtractionFailed must carry the spend of all billed attempts so the budget reconciles it.
    client = _ScriptedClient([INVALID_JSON, INVALID_JSON], cost_usd=0.5)
    with pytest.raises(ExtractionFailed) as excinfo:
        run_extraction(client, InvoiceV1, system="sys", content="doc")
    assert excinfo.value.cost_usd == pytest.approx(1.0)  # 2 billed attempts x 0.5


def test_provider_error_on_second_attempt_carries_prior_cost():
    # The first (validation-failing) attempt was billed; the provider error on the retry must
    # carry that already-incurred spend so the budget still counts it.
    client = _ScriptedClient(
        [INVALID_JSON, ProviderTimeout(provider="fake", detail="slow")], cost_usd=0.5
    )
    with pytest.raises(ProviderTimeout) as excinfo:
        run_extraction(client, InvoiceV1, system="sys", content="doc")
    assert excinfo.value.cost_usd == pytest.approx(0.5)


def test_provider_error_on_first_attempt_carries_zero_cost():
    # Nothing was billed before the first call failed, so the carried cost is 0 when the
    # failed call's own cost is unknown (a timeout raises before any usage is read).
    client = _ScriptedClient([ProviderTimeout(provider="fake", detail="slow")], cost_usd=0.5)
    with pytest.raises(ProviderTimeout) as excinfo:
        run_extraction(client, InvoiceV1, system="sys", content="doc")
    assert excinfo.value.cost_usd == 0.0


def test_refusal_on_first_attempt_carries_its_own_billed_cost():
    # A refusal/truncation is a billed response; the client sets the failed call's own cost
    # on the exception, and the pipeline must preserve it (prior spend here is 0).
    client = _ScriptedClient([ProviderRefusal(provider="fake", reason="bio", cost_usd=0.3)])
    with pytest.raises(ProviderRefusal) as excinfo:
        run_extraction(client, InvoiceV1, system="sys", content="doc")
    assert excinfo.value.cost_usd == pytest.approx(0.3)


def test_truncation_on_second_attempt_adds_prior_and_own_cost():
    # First attempt is billed (validation miss); the retry truncates (billed). The carried
    # cost must be prior-attempt spend PLUS the truncated call's own cost.
    client = _ScriptedClient(
        [INVALID_JSON, ProviderTruncation(provider="fake", reason="max_tokens", cost_usd=0.3)],
        cost_usd=0.5,
    )
    with pytest.raises(ProviderTruncation) as excinfo:
        run_extraction(client, InvoiceV1, system="sys", content="doc")
    assert excinfo.value.cost_usd == pytest.approx(0.8)  # 0.5 prior + 0.3 own
