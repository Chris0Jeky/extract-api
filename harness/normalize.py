"""Deterministic normalization helpers for the accuracy harness.

Dates -> ISO 8601 (YYYY-MM-DD); money -> integer minor units (currency-aware).
Deterministic and dependency-free; no LLM anywhere. Fail loud: ambiguous or
out-of-range input raises rather than being coerced or guessed, so the accuracy
harness never compares a silently-mangled value.

Two conventions are committed here (documented, not guessed):
- Numeric slash/dash dates are read DAY-FIRST (DD/MM/YYYY), the UK convention this
  service targets. ISO input is detected first and never reinterpreted.
- Minor-unit digits follow ISO-4217: default 2, with the standard 0-digit and 3-digit
  exceptions listed below. The currency must be a known ISO-4217 code.

Month-name dates (for example "15 January 2026") are intentionally NOT parsed: strptime
month names are locale-dependent, which would break determinism. The schema already
requires ISO dates from the model, so the harness only needs ISO plus the numeric forms.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from schemas.iso4217 import ISO_4217_ALPHA

# Explicit, ordered numeric formats tried after ISO, all day-first. Locale-independent
# (no month names). Anything else raises (no fuzzy parsing).
_DATE_FORMATS: tuple[str, ...] = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
)

# ISO-4217 minor-unit exceptions to the default of 2. Sourced from the standard; every
# code here is a member of ISO_4217_ALPHA (asserted by the tests).
_ZERO_DECIMAL: frozenset[str] = frozenset(
    {
        "BIF",
        "CLP",
        "DJF",
        "GNF",
        "ISK",
        "JPY",
        "KMF",
        "KRW",
        "PYG",
        "RWF",
        "UGX",
        "VND",
        "VUV",
        "XAF",
        "XOF",
        "XPF",
    }
)
_THREE_DECIMAL: frozenset[str] = frozenset({"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"})


def to_iso_date(value: str) -> str:
    """Normalize a date string to ISO-8601 (YYYY-MM-DD), or raise on bad input.

    ISO input is validated and returned canonical; numeric slash/dash dates are read
    day-first (UK). Raises ValueError on anything that does not match a known format or
    is not a real calendar date (e.g. 2026-13-01, 31/02/2026).
    """
    text = value.strip()
    if not text:
        raise ValueError("date is empty")
    # ISO first so an already-normalized value is never reinterpreted as day-first.
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unrecognized or invalid date: {value!r}")


def _minor_digits(currency: str) -> int:
    if currency not in ISO_4217_ALPHA:
        raise ValueError(f"unknown ISO-4217 currency code: {currency!r}")
    if currency in _ZERO_DECIMAL:
        return 0
    if currency in _THREE_DECIMAL:
        return 3
    return 2


def to_minor_units(amount: str, currency: str) -> int:
    """Convert a money amount to integer minor units for the given ISO-4217 code.

    `amount` is a decimal string (dot decimal separator; commas are treated as thousands
    separators and stripped). Raises ValueError if the currency is unknown, the amount is
    not a finite decimal, or it carries more fractional digits than the currency permits
    (e.g. "100.001" GBP, "100.5" JPY) - those are failed loudly, never rounded.
    """
    digits = _minor_digits(currency)
    cleaned = amount.strip().replace(",", "")
    if not cleaned:
        raise ValueError("amount is empty")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"amount {amount!r} is not a valid decimal number") from exc
    if not value.is_finite():
        raise ValueError(f"amount {amount!r} is not a finite number")
    # Fractional-digit count = -exponent when the exponent is negative. A finite Decimal
    # always has an int exponent (the 'n'/'F' sentinels are NaN/Infinity only, excluded
    # above); assert it so the type narrows.
    exponent = value.as_tuple().exponent
    assert isinstance(exponent, int)
    fractional = max(0, -exponent)
    if fractional > digits:
        raise ValueError(
            f"amount {amount!r} has {fractional} fractional digits but {currency} allows {digits}"
        )
    # The fractional-digit check above guarantees value * 10^digits is an integer, so
    # scaleb is exact and int() truncates nothing.
    return int(value.scaleb(digits))
