"""SessionStart hook: orient a fresh session toward the rules and the backlog."""

from __future__ import annotations


def main() -> int:
    print(
        "extract-api: read CLAUDE.md + AGENTS.md before changing code. "
        "Next work is the next unblocked task in tasks/BACKLOG.md. "
        "Fail loud, never silently coerce; provider SDKs only in llm/client.py; "
        "small conventional commits; no secrets; no em dashes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
