"""SessionStart hook: orient a fresh session toward the rules and the backlog."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
# Windows venvs put the interpreter under Scripts/, POSIX venvs (Linux CI, macOS) under
# bin/. Printing one hard-coded form hands half of all sessions a gate command that dies
# before a single check runs, so probe for the one that exists.
_VENV_PYTHONS = (".venv/Scripts/python.exe", ".venv/bin/python")


def venv_python() -> str:
    """Repo-relative venv interpreter for this platform, or a bare `python` fallback."""
    for relative in _VENV_PYTHONS:
        if (_ROOT / relative).exists():
            return relative
    return "python"


def main() -> int:
    print(
        "extract-api (T2, push+merge free): CLAUDE.md has the region map, the measured "
        "proving-checks table, and the pitfalls. Next work is the next unblocked task in "
        f"tasks/BACKLOG.md. Gate: make PYTHON={venv_python()} ci-quick; a targeted "
        "pytest slice needs --no-cov or the coverage ratchet fails it. Fail loud, never "
        "silently coerce; provider SDKs only in llm/client.py; no secrets; no em dashes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
