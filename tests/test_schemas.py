"""Strict-schema behavior: validate the good case and that bad cases fail loudly."""

import json

import pytest
from pydantic import ValidationError

from schemas.invoice_v1 import InvoiceV1
from schemas.job_posting_v1 import JobPostingV1

VALID_INVOICE = {
    "invoice_number": "INV-001",
    "issue_date": "2026-01-15",
    "due_date": None,
    "currency": "GBP",
    "subtotal_minor": 10000,
    "tax_minor": 2000,
    "total_minor": 12000,
    "vendor_name": "Acme Ltd",
    "vendor_tax_id": None,
    "buyer_name": None,
    "line_items": [
        {"description": "Widget", "quantity": 2, "unit_price_minor": 5000, "amount_minor": 10000}
    ],
}

VALID_JOB = {
    "title": "Senior Engineer",
    "company": None,
    "location": "London",
    "remote_policy": "hybrid",
    "salary_min": 5000000,
    "salary_max": 7000000,
    "salary_currency": "GBP",
    "salary_period": "year",
    "employment_type": "full_time",
    "seniority": "senior",
    "visa_sponsorship": "offered",
    "posted_date": None,
}


def test_invoice_valid_from_json():
    inv = InvoiceV1.model_validate_json(json.dumps(VALID_INVOICE))
    assert inv.invoice_number == "INV-001"
    assert inv.issue_date.isoformat() == "2026-01-15"
    assert inv.line_items is not None and inv.line_items[0].amount_minor == 10000


def test_invoice_missing_required_field_fails():
    payload = dict(VALID_INVOICE)
    del payload["invoice_number"]
    with pytest.raises(ValidationError):
        InvoiceV1.model_validate_json(json.dumps(payload))


def test_invoice_strict_rejects_string_for_int():
    payload = dict(VALID_INVOICE)
    payload["total_minor"] = "12000"  # strict: a JSON string is not an int
    with pytest.raises(ValidationError):
        InvoiceV1.model_validate_json(json.dumps(payload))


def test_invoice_rejects_bad_currency():
    payload = dict(VALID_INVOICE)
    payload["currency"] = "pounds"
    with pytest.raises(ValidationError):
        InvoiceV1.model_validate_json(json.dumps(payload))


def test_invoice_rejects_non_ascii_currency_lookalikes():
    # Unicode look-alikes must fail the ASCII format gate: Cyrillic ABV,
    # Greek GBD, fullwidth-Latin GBP. isalpha()/isupper() alone would pass them.
    for bogus in ("АБВ", "ΓΒΔ", "ＧＢＰ"):
        payload = dict(VALID_INVOICE)
        payload["currency"] = bogus
        with pytest.raises(ValidationError):
            InvoiceV1.model_validate_json(json.dumps(payload))


def test_invoice_extra_field_forbidden():
    payload = dict(VALID_INVOICE)
    payload["mystery"] = "x"
    with pytest.raises(ValidationError):
        InvoiceV1.model_validate_json(json.dumps(payload))


def test_job_valid_from_json():
    job = JobPostingV1.model_validate_json(json.dumps(VALID_JOB))
    assert job.remote_policy.value == "hybrid"
    assert job.salary_max == 7000000


def test_job_salary_inverted_range_fails():
    payload = dict(VALID_JOB)
    payload["salary_min"] = 7000000
    payload["salary_max"] = 5000000
    with pytest.raises(ValidationError):
        JobPostingV1.model_validate_json(json.dumps(payload))


def test_job_salary_competitive_string_fails():
    payload = dict(VALID_JOB)
    payload["salary_max"] = "competitive"  # the canonical retry exemplar
    with pytest.raises(ValidationError):
        JobPostingV1.model_validate_json(json.dumps(payload))


def test_job_unknown_enum_value_fails():
    payload = dict(VALID_JOB)
    payload["remote_policy"] = "telepathic"
    with pytest.raises(ValidationError):
        JobPostingV1.model_validate_json(json.dumps(payload))
