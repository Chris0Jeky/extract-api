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

# Cover the project's own key formats (OPENAI_API_KEY sk-proj-..., ANTHROPIC_API_KEY
# sk-ant-...) plus GitHub tokens and AWS keys. The legacy `sk-[A-Za-z0-9]{16,}` run
# stopped at the first hyphen, leaking modern hyphenated/prefixed keys verbatim.
_SECRET = re.compile(
    r"sk-[A-Za-z0-9_-]{16,}"  # OpenAI legacy/sk-proj- and Anthropic sk-ant-
    r"|gh[pousr]_[A-Za-z0-9]{36,}"  # GitHub ghp_/gho_/ghu_/ghs_/ghr_ tokens
    r"|github_pat_[A-Za-z0-9_]{40,}"  # GitHub fine-grained PAT
    r"|AKIA[0-9A-Z]{16}"  # AWS access key id
    # Whole PEM block (header + body + footer), falling back to the header alone if the
    # block is truncated; otherwise only the header was scrubbed and the key body leaked.
    r"|-----BEGIN[A-Z ]*PRIVATE KEY-----(?:[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----)?"
)


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
