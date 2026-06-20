"""invoice.v1 strict schema.

Field specs are authoritative from the handover. Normalization rules: dates are
ISO-8601 (the `date` type parses ISO strings when validating JSON), money is
integer minor units, currency is ISO-4217, and a genuinely-absent field is null.

Nullable fields are required-but-nullable (no default): a provider must emit the
key, as an explicit null when the value is genuinely absent, so omission fails
loudly and the generated JSON schema marks every field required (ADR 0002).
Aggregate arithmetic consistency is enforced after parse and is a validation-retry
trigger.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, model_validator

from schemas._common import STRICT_CONFIG, CurrencyCode


class LineItem(BaseModel):
    model_config = STRICT_CONFIG

    description: str
    # quantity may be fractional (ratified pack proposal); int | float accepts both.
    quantity: int | float
    unit_price_minor: int
    amount_minor: int


class InvoiceV1(BaseModel):
    model_config = STRICT_CONFIG

    invoice_number: str
    issue_date: date
    due_date: date | None
    currency: CurrencyCode
    subtotal_minor: int
    tax_minor: int | None
    total_minor: int
    vendor_name: str
    vendor_tax_id: str | None
    buyer_name: str | None
    line_items: list[LineItem] | None

    @model_validator(mode="after")
    def _check_totals(self) -> InvoiceV1:
        # total = subtotal + tax. tax may be genuinely absent (null) -> treat as 0.
        tax = self.tax_minor if self.tax_minor is not None else 0
        expected_total = self.subtotal_minor + tax
        if self.total_minor != expected_total:
            raise ValueError(
                f"total_minor ({self.total_minor}) must equal subtotal_minor "
                f"({self.subtotal_minor}) + tax_minor ({tax})"
            )
        # Line items, when present, must be a non-empty itemization that sums to the
        # subtotal. An empty list is rejected: under the explicit-null contract a
        # provider with no itemization emits null, not []. Per-line amount vs
        # quantity*unit_price is deliberately NOT enforced (legitimate per-line
        # discounts and rounding; amount_minor is the authoritative value; issue #2).
        if self.line_items is not None:
            if not self.line_items:
                raise ValueError("line_items must be null when absent, not an empty list")
            line_sum = sum(item.amount_minor for item in self.line_items)
            if self.subtotal_minor != line_sum:
                raise ValueError(
                    f"subtotal_minor ({self.subtotal_minor}) must equal the sum of "
                    f"line item amounts ({line_sum})"
                )
        return self
