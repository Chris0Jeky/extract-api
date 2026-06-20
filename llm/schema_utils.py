"""Make a Pydantic JSON schema safe for the providers' structured-output subset.

ADR 0002: the providers' JSON-schema subset guarantees SHAPE (types, required-ness)
but does not support value-constraint keywords (format, pattern, numeric bounds,
string length). Those constraints live in Pydantic and run after parse (the
validation-retry loop is what enforces them), so we strip them before sending the
schema to a provider rather than risk the schema being rejected. Tracks issue #9.
"""

from __future__ import annotations

import copy
from typing import cast

# Keywords the provider strict-json-schema subset does not support. Stripping them
# keeps the shape (type / properties / required / enum) while dropping the value
# constraints that Pydantic re-checks after parse.
UNSUPPORTED_KEYWORDS: frozenset[str] = frozenset(
    {
        "format",
        "pattern",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "multipleOf",
        "minItems",
        "maxItems",
        "uniqueItems",
    }
)


def sanitize_for_provider(schema: dict[str, object]) -> dict[str, object]:
    """Return a deep copy of `schema` with unsupported keywords removed at every depth.

    Never mutates the input. Recurses through dicts and lists so nested object,
    array-item, and $defs schemas are all sanitized.
    """
    # The top-level schema is always an object; _strip preserves that shape.
    return cast("dict[str, object]", _strip(copy.deepcopy(schema)))


def _strip(node: object) -> object:
    if isinstance(node, dict):
        return {
            key: _strip(value) for key, value in node.items() if key not in UNSUPPORTED_KEYWORDS
        }
    if isinstance(node, list):
        return [_strip(item) for item in node]
    return node
