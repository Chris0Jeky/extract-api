"""PostToolUse hook: append a secret-redacted line to the failure ledger.

Best-effort and defensive: it never raises and always exits 0, so it can never
break a tool call. It only records when the tool result signals an error. The
ledger (.claude/local/failure_ledger.jsonl) is gitignored.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_SECRET = re.compile(r"sk-[A-Za-z0-9]{16,}|-----BEGIN[A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}")


def _redact(text: str) -> str:
    return _SECRET.sub("[REDACTED]", text)


def _looks_like_failure(payload: dict[str, object]) -> bool:
    response = payload.get("tool_response")
    blob = json.dumps(response) if response is not None else json.dumps(payload)
    return any(token in blob.lower() for token in ('"error"', "is_error", "traceback", "stderr"))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        if not isinstance(payload, dict) or not _looks_like_failure(payload):
            return 0
        project = os.environ.get("CLAUDE_PROJECT_DIR", ".")
        ledger = Path(project) / ".claude" / "local" / "failure_ledger.jsonl"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "tool": payload.get("tool_name", "?"),
            "summary": _redact(json.dumps(payload))[:2000],
        }
        with ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
