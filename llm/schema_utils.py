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

# Keys whose value is a mapping of NAME -> subschema. The inner keys are property /
# definition names (which may legitimately equal a constraint keyword, e.g. a field
# literally named "format"), so they must be kept; only the subschema values are
# sanitized. Stripping by name at any depth would wrongly delete such a property.
_SCHEMA_MAP_KEYS: frozenset[str] = frozenset(
    {"properties", "$defs", "definitions", "patternProperties", "dependentSchemas"}
)


def sanitize_for_provider(schema: dict[str, object]) -> dict[str, object]:
    """Return a deep copy of `schema` with unsupported keywords removed at every depth.

    Never mutates the input. Stripping is keyword-position-aware: an unsupported
    keyword is dropped only where it is a schema keyword, not where it is a property
    or definition name (see `_SCHEMA_MAP_KEYS`).
    """
    # The top-level schema is always an object; _strip preserves that shape.
    return cast("dict[str, object]", _strip(copy.deepcopy(schema)))


def _strip(node: object) -> object:
    if isinstance(node, dict):
        result: dict[str, object] = {}
        for key, value in node.items():
            if key in UNSUPPORTED_KEYWORDS:
                continue  # drop the unsupported constraint keyword at this schema node
            if key in _SCHEMA_MAP_KEYS and isinstance(value, dict):
                # value maps names to subschemas: keep the names, sanitize the values.
                result[key] = {name: _strip(sub) for name, sub in value.items()}
            else:
                result[key] = _strip(value)
        return result
    if isinstance(node, list):
        return [_strip(item) for item in node]
    return node
