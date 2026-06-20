"""sanitize_for_provider strips unsupported keywords at every depth, without mutating."""

from llm.schema_utils import sanitize_for_provider


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
