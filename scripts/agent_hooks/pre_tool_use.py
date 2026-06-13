"""PreToolUse safety hook: block destructive or secret-leaking shell commands.

Reads the Claude Code tool-call JSON on stdin and prints a deny decision when a
Bash command is dangerous. The decision logic lives in decide() so smoke_test.py
can verify it directly. Defense in depth: this runs even under bypassPermissions.
"""

from __future__ import annotations

import json
import re
import sys

_RM = re.compile(r"\brm\b", re.IGNORECASE)
_RM_FLAG = re.compile(r"(?:^|\s)-\w*[rf]|--recursive|--force", re.IGNORECASE)
_RM_TARGET = re.compile(r"(?:^|\s)(?:/|~|~/|/\*|\$HOME)(?:\s|$)")

_DENY_PATTERNS = [
    (
        re.compile(r"\bgit\s+push\b.*(?:--force\b(?!-with-lease)|\s-f\b)", re.IGNORECASE),
        "Bare force-push is blocked; use --force-with-lease.",
    ),
    (
        re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE),
        "git reset --hard is blocked; explain before discarding work.",
    ),
    (re.compile(r"\bsudo\b", re.IGNORECASE), "sudo is blocked."),
    (
        re.compile(r"\b(?:curl|wget)\b[^|]*\|\s*(?:sudo\s+)?(?:ba)?sh\b", re.IGNORECASE),
        "Piping a remote download into a shell is blocked.",
    ),
]

_SECRET_VALUE = re.compile(
    r"sk-[A-Za-z0-9]{16,}|-----BEGIN[A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}"
)
_WRITE_INTENT = re.compile(r">>?|\btee\b|\bset-content\b|\bout-file\b", re.IGNORECASE)


def _is_dangerous_rm(command: str) -> bool:
    return bool(_RM.search(command) and _RM_FLAG.search(command) and _RM_TARGET.search(command))


def decide(command: str) -> tuple[str, str]:
    """Return ("deny", reason) for dangerous commands, else ("allow", "")."""
    compact = " ".join(command.split())
    if _is_dangerous_rm(compact):
        return "deny", "Refusing a recursive delete that targets / or ~."
    for pattern, reason in _DENY_PATTERNS:
        if pattern.search(compact):
            return "deny", reason
    if _SECRET_VALUE.search(compact) and _WRITE_INTENT.search(compact):
        return "deny", "Command appears to write secret or credential material to a file."
    return "allow", ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    command = ""
    if payload.get("tool_name") == "Bash":
        command = payload.get("tool_input", {}).get("command", "")
    decision, reason = decide(command) if command else ("allow", "")
    if decision == "deny":
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
