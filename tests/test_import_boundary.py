"""Gateway-seam invariant: only llm/client.py may import a provider SDK."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVIDER_IMPORT = re.compile(r"^\s*(?:import|from)\s+(?:openai|anthropic)\b", re.MULTILINE)


def _modules_outside_client():
    for pkg in ("api", "schemas", "harness", "llm"):
        for path in (ROOT / pkg).rglob("*.py"):
            if path.name == "client.py" and path.parent.name == "llm":
                continue
            yield path


def test_no_provider_sdk_import_outside_client():
    offenders = [
        str(path.relative_to(ROOT))
        for path in _modules_outside_client()
        if PROVIDER_IMPORT.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"provider SDK imported outside llm/client.py: {offenders}"
