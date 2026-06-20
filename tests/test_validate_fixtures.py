"""validate_fixtures fails loud (not AttributeError) when a fixture is not an object."""

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validate_fixtures.py"
_spec = importlib.util.spec_from_file_location("validate_fixtures", _SCRIPT)
assert _spec is not None and _spec.loader is not None
validate_fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate_fixtures)


def test_list_fixture_reports_object_error(tmp_path):
    path = tmp_path / "bad_list.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    errs = validate_fixtures.validate_file(path)
    assert errs == [f"{path.name}: fixture must be a JSON object, got list"]


def test_scalar_fixture_reports_object_error(tmp_path):
    path = tmp_path / "bad_scalar.json"
    path.write_text("42", encoding="utf-8")
    errs = validate_fixtures.validate_file(path)
    assert len(errs) == 1
    assert "must be a JSON object" in errs[0]


def test_invalid_json_reports_error(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    errs = validate_fixtures.validate_file(path)
    assert len(errs) == 1
    assert "invalid JSON" in errs[0]
