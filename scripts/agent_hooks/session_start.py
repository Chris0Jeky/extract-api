"""SessionStart hook: orient a fresh session toward the rules and the backlog."""

from __future__ import annotations


def main() -> int:
    print(
        "extract-api (T2, push+merge free): CLAUDE.md has the region map, the measured "
        "proving-checks table, and the pitfalls. Next work is the next unblocked task in "
        "tasks/BACKLOG.md. Gate: make PYTHON=.venv/Scripts/python ci-quick; a targeted "
        "pytest slice needs --no-cov or the coverage ratchet fails it. Fail loud, never "
        "silently coerce; provider SDKs only in llm/client.py; no secrets; no em dashes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
