"""Shared building blocks for the strict extraction schemas.

Design notes (see docs/adr/0002-structured-output-mode.md):
- Every model is strict (no silent coercion) and forbids extra fields, mirroring
  the providers' additionalProperties:false.
- Optional fields are null-unions (X | None) so a provider's strict structured
  output schema stays valid while still allowing an explicit null for a
  genuinely-absent field.
- Value constraints the providers cannot enforce in their JSON-schema subset
  (ISO-4217 membership, cross-field relations) live here as validators and run
  after parse. A failure here is what triggers the validation-retry loop.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, ConfigDict

# strict=True: type mismatches raise instead of coercing.
# extra="forbid": unknown keys raise (pack-derived hardening, ADR 0002).
STRICT_CONFIG = ConfigDict(strict=True, extra="forbid")


def _validate_iso4217(value: str) -> str:
    """Format-level ISO-4217 check.

    v1 enforces the 3-letter uppercase ASCII shape; full code-set membership is
    tightened in T01 against a committed ISO-4217 table. The ASCII guard matters:
    `str.isalpha`/`str.isupper` are unicode-aware, so without it Cyrillic/Greek/
    fullwidth look-alikes (e.g. U+0410U+0411U+0412) would pass and a homoglyph
    currency would slip through instead of failing loudly.
    """
    if len(value) != 3 or not value.isascii() or not value.isalpha() or not value.isupper():
        raise ValueError("currency must be a 3-letter uppercase ASCII ISO-4217 code")
    return value


CurrencyCode = Annotated[str, AfterValidator(_validate_iso4217)]
