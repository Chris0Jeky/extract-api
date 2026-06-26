"""sanitize_for_provider strips unsupported keywords at every depth, without mutating."""

from llm.schema_utils import UNSUPPORTED_KEYWORDS, sanitize_for_provider
from schemas.invoice_v1 import InvoiceV1
from schemas.job_posting_v1 import JobPostingV1


def test_sanitize_strips_nested_unsupported_keywords():
    schema = {
        "type": "object",
        "properties": {
            "d": {"type": "string", "format": "date"},
            "n": {"type": "integer", "minimum": 0, "maximum": 10},
            "items": {
                "type": "array",
                "items": {"type": "string", "pattern": "^x"},
                "minItems": 1,
            },
        },
        "required": ["d"],
    }
    out = sanitize_for_provider(schema)
    assert "format" not in out["properties"]["d"]
    assert "minimum" not in out["properties"]["n"]
    assert "maximum" not in out["properties"]["n"]
    assert "pattern" not in out["properties"]["items"]["items"]
    assert "minItems" not in out["properties"]["items"]


def test_sanitize_preserves_shape_and_does_not_mutate_input():
    schema = {
        "type": "object",
        "properties": {"d": {"type": "string", "format": "date"}},
        "required": ["d"],
    }
    out = sanitize_for_provider(schema)
    assert out["properties"]["d"]["type"] == "string"
    assert out["required"] == ["d"]
    # input untouched
    assert "format" in schema["properties"]["d"]


def test_property_named_like_a_keyword_is_preserved():
    # Stripping is position-aware: a property literally named "format"/"pattern" must
    # survive; only the constraint keyword at a schema node is removed.
    schema = {
        "type": "object",
        "properties": {
            "format": {"type": "string", "format": "date"},
            "pattern": {"type": "integer", "minimum": 0},
        },
        "required": ["format", "pattern"],
    }
    out = sanitize_for_provider(schema)
    assert "format" in out["properties"]
    assert "pattern" in out["properties"]
    assert "format" not in out["properties"]["format"]  # the date-format constraint is gone
    assert "minimum" not in out["properties"]["pattern"]
    assert out["required"] == ["format", "pattern"]


def _has_unsupported_keyword(node) -> bool:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("properties", "$defs", "definitions"):
                if any(_has_unsupported_keyword(sub) for sub in value.values()):
                    return True
                continue
            if key in UNSUPPORTED_KEYWORDS:
                return True
            if _has_unsupported_keyword(value):
                return True
    elif isinstance(node, list):
        return any(_has_unsupported_keyword(item) for item in node)
    return False


def test_real_invoice_schema_survives_sanitize_and_is_provider_strict():
    san = sanitize_for_provider(InvoiceV1.model_json_schema())
    # top-level object is strict-valid for the provider: closed + every field required
    assert san["additionalProperties"] is False
    assert set(san["required"]) == set(san["properties"])
    # nested $defs (LineItem) are also strict-valid
    for sub in san.get("$defs", {}).values():
        if sub.get("type") == "object":
            assert sub["additionalProperties"] is False
            assert set(sub["required"]) == set(sub["properties"])
    # the date `format` keyword was stripped everywhere; no unsupported keyword remains
    assert "format" not in san["properties"]["issue_date"]
    assert not _has_unsupported_keyword(san)


def test_real_job_posting_schema_survives_sanitize_and_is_provider_strict():
    # Parity with invoice (issue #8 / ADR 0002): job_posting.v1 must be OpenAI-strict too.
    san = sanitize_for_provider(JobPostingV1.model_json_schema())
    assert san["additionalProperties"] is False
    assert set(san["required"]) == set(san["properties"])
    # the date `format` here is nested inside posted_date's null-union (anyOf), a deeper
    # case than invoice's top-level date; it and every other unsupported keyword are gone.
    assert not _has_unsupported_keyword(san)
    # enum $defs survive sanitization (providers support enum); each is a string enum.
    enum_defs = [sub for sub in san.get("$defs", {}).values() if "enum" in sub]
    assert enum_defs  # the job schema has enum fields (remote_policy, etc.)
    for sub in enum_defs:
        assert sub.get("type") == "string"
