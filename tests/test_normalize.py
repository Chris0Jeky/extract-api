"""harness.normalize: date -> ISO and money -> minor units, failing loud on bad input."""

import pytest

from harness.normalize import (
    _THREE_DECIMAL,
    _ZERO_DECIMAL,
    to_iso_date,
    to_minor_units,
)
from schemas.iso4217 import ISO_4217_ALPHA

# --- dates ---------------------------------------------------------------------------


def test_iso_passthrough_is_canonical():
    assert to_iso_date("2026-01-15") == "2026-01-15"
    assert to_iso_date("  2026-01-15  ") == "2026-01-15"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("15/01/2026", "2026-01-15"),
        ("15-01-2026", "2026-01-15"),
        ("15.01.2026", "2026-01-15"),
        ("01/02/2026", "2026-02-01"),  # day-first convention (not Feb 1 US-style)
    ],
)
def test_numeric_dates_are_read_day_first(raw, expected):
    assert to_iso_date(raw) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "garbage",
        "2026-13-01",  # invalid month
        "2026-02-30",  # invalid day
        "31/02/2026",  # invalid day for February
        "13/13/2026",  # invalid month day-first
        "01/15/2026",  # US month-first is not accepted (month 15 invalid)
        "15 January 2026",  # month names intentionally unsupported (locale)
    ],
)
def test_bad_dates_raise_not_coerce(bad):
    with pytest.raises(ValueError):
        to_iso_date(bad)


# --- money ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "currency", "minor"),
    [
        ("100.00", "GBP", 10000),
        ("100", "GBP", 10000),
        ("100.5", "GBP", 10050),
        ("0.99", "USD", 99),
        ("1,234.56", "EUR", 123456),
        ("-50.00", "GBP", -5000),  # credit notes are legitimate
        ("100", "JPY", 100),  # 0-digit currency
        ("1.234", "BHD", 1234),  # 3-digit currency
    ],
)
def test_money_to_minor_units(amount, currency, minor):
    assert to_minor_units(amount, currency) == minor


@pytest.mark.parametrize(
    ("amount", "currency"),
    [
        ("100.001", "GBP"),  # too many fractional digits for 2-digit currency
        ("100.5", "JPY"),  # any fraction is too precise for a 0-digit currency
        ("1.2345", "BHD"),  # 4 digits for a 3-digit currency
        ("abc", "GBP"),
        ("", "GBP"),
        ("inf", "GBP"),
        ("nan", "GBP"),
        ("100.00", "ZZZ"),  # unknown currency
        ("100.00", "gbp"),  # lowercase is not a valid ISO-4217 code
    ],
)
def test_bad_money_raises_not_coerce(amount, currency):
    with pytest.raises(ValueError):
        to_minor_units(amount, currency)


def test_minor_digit_tables_are_subset_of_known_currencies():
    # Guards against an exception list drifting out of the committed ISO-4217 set.
    assert _ZERO_DECIMAL <= ISO_4217_ALPHA
    assert _THREE_DECIMAL <= ISO_4217_ALPHA
    assert _ZERO_DECIMAL.isdisjoint(_THREE_DECIMAL)
