"""Deterministic normalization helpers for the accuracy harness.

Dates -> ISO 8601; money -> integer minor units (currency-aware). Deterministic
and dependency-free; no LLM anywhere. Real logic lands in T06.
"""

from __future__ import annotations

# Minor-unit digits per ISO-4217. Most currencies use 2; JPY/KRW use 0; a few use
# 3. The full table is committed in T06; this note records the shape.
DEFAULT_MINOR_DIGITS = 2


def to_iso_date(value: str) -> str:
    """Normalize a date string to ISO-8601 (YYYY-MM-DD), or raise on bad input."""
    raise NotImplementedError("date -> ISO 8601 normalization lands in T06")


def to_minor_units(amount: str, currency: str) -> int:
    """Convert a money amount to integer minor units for the given ISO-4217 code."""
    raise NotImplementedError("money -> integer minor units lands in T06")
