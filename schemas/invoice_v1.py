"""invoice.v1 strict schema.

Field specs are authoritative from the handover. Normalization rules: dates are
ISO-8601 (the `date` type parses ISO strings when validating JSON), money is
integer minor units, currency is ISO-4217, and a genuinely-absent field is null.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

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
    due_date: date | None = None
    currency: CurrencyCode
    subtotal_minor: int
    tax_minor: int | None = None
    total_minor: int
    vendor_name: str
    vendor_tax_id: str | None = None
    buyer_name: str | None = None
    line_items: list[LineItem] | None = None
