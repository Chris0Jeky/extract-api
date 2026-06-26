"""`make smoke` runs fully offline: app boots, /v1/extract 200 + forced 422, env clean."""

import importlib.util
import os
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "smoke.py"
_spec = importlib.util.spec_from_file_location("smoke", _SCRIPT)
assert _spec is not None and _spec.loader is not None
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)


def test_smoke_passes_offline(capsys):
    assert smoke.main() == 0
    assert "SMOKE OK" in capsys.readouterr().out


def test_smoke_does_not_leak_fixture_env(monkeypatch):
    # main() pins LLM_PROVIDER_MODE / FIXTURE_CANNED_TEXT for the fixture client; it must
    # restore them so it never leaks the offline routing into a real environment.
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    monkeypatch.delenv("FIXTURE_CANNED_TEXT", raising=False)
    assert smoke.main() == 0
    assert "LLM_PROVIDER_MODE" not in os.environ
    assert "FIXTURE_CANNED_TEXT" not in os.environ
