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
    # Unicode look-alikes must fail the ASCII format gate. Written as escapes so the
    # literals are unambiguous: Cyrillic ABV, Greek look-alikes, fullwidth-Latin GBP.
    # isalpha()/isupper() alone would pass all three.
    for bogus in ("\u0410\u0411\u0412", "\u0393\u0392\u0394", "\uff27\uff22\uff30"):
        payload = dict(VALID_INVOICE)
        payload["currency"] = bogus
        with pytest.raises(ValidationError):
            InvoiceV1.model_validate_json(json.dumps(payload))


def test_invoice_extra_field_forbidden():
    payload = dict(VALID_INVOICE)
    payload["mystery"] = "x"
    with pytest.raises(ValidationError):
        InvoiceV1.model_validate_json(json.dumps(payload))


def test_invoice_rejects_well_shaped_but_unknown_currency():
    # Correct shape, but not a real ISO-4217 code -> membership failure.
    for bogus in ("ZZZ", "ABC", "QQQ"):
        payload = dict(VALID_INVOICE)
        payload["currency"] = bogus
        with pytest.raises(ValidationError):
            InvoiceV1.model_validate_json(json.dumps(payload))


def test_invoice_accepts_each_fixture_currency():
    for code in ("GBP", "USD", "EUR", "JPY"):
        payload = dict(VALID_INVOICE)
        payload["currency"] = code
        InvoiceV1.model_validate_json(json.dumps(payload))  # must not raise


def test_invoice_total_must_equal_subtotal_plus_tax():
    payload = dict(VALID_INVOICE)
    payload["total_minor"] = 99999  # != subtotal (10000) + tax (2000)
    with pytest.raises(ValidationError):
        InvoiceV1.model_validate_json(json.dumps(payload))


def test_invoice_tax_null_means_total_equals_subtotal():
    payload = dict(VALID_INVOICE)
    payload["tax_minor"] = None
    payload["total_minor"] = payload["subtotal_minor"]
    payload["line_items"] = None  # isolate the totals check from the line-item sum
    InvoiceV1.model_validate_json(json.dumps(payload))  # must not raise


def test_invoice_line_items_must_sum_to_subtotal():
    payload = dict(VALID_INVOICE)
    # subtotal stays 10000 but the single line now sums to 9000
    payload["line_items"] = [
        {"description": "Widget", "quantity": 1, "unit_price_minor": 9000, "amount_minor": 9000}
    ]
    with pytest.raises(ValidationError):
        InvoiceV1.model_validate_json(json.dumps(payload))


def test_invoice_line_item_wrong_type_fails():
    payload = dict(VALID_INVOICE)
    payload["line_items"] = [
        {
            "description": "Widget",
            "quantity": "two",
            "unit_price_minor": 5000,
            "amount_minor": 10000,
        }
    ]
    with pytest.raises(ValidationError):
        InvoiceV1.model_validate_json(json.dumps(payload))


def test_invoice_omitting_nullable_key_fails():
    # due_date is required-but-nullable: the key must be present (explicit null),
    # so omitting it entirely must fail (ADR 0002 explicit-null contract).
    payload = dict(VALID_INVOICE)
    del payload["due_date"]
    with pytest.raises(ValidationError):
        InvoiceV1.model_validate_json(json.dumps(payload))


def test_invoice_empty_line_items_list_rejected():
    # Explicit-null contract: an absent itemization must be null, never [].
    payload = dict(VALID_INVOICE)
    payload["line_items"] = []
    with pytest.raises(ValidationError):
        InvoiceV1.model_validate_json(json.dumps(payload))


def test_invoice_schema_marks_every_field_required():
    # Issue #3 acceptance: explicit-null means the JSON schema requires every key.
    schema = InvoiceV1.model_json_schema()
    assert set(schema["required"]) == set(schema["properties"])


def test_invoice_tax_null_with_line_items_validates():
    # The tax-null AND line-items-present combination must validate when consistent.
    payload = dict(VALID_INVOICE)
    payload["tax_minor"] = None
    payload["total_minor"] = payload["subtotal_minor"]  # line items already sum to it
    InvoiceV1.model_validate_json(json.dumps(payload))  # must not raise


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
