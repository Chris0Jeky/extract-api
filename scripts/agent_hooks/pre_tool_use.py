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
# Match a catastrophic delete target, tolerating optional surrounding quotes and a
# trailing slash so `rm -rf "/"`, `rm -rf '$HOME'`, and `rm -rf $HOME/` cannot slip
# past the boundary anchors. `/?` lets `~` cover `~/` and `$HOME` cover `$HOME/`;
# `\$\{?HOME\}?` covers both `$HOME` and the braced `${HOME}` expansion.
_RM_TARGET = re.compile(r"""(?:^|\s)['"]?(?:/|~|/\*|\$\{?HOME\}?)/?['"]?(?:\s|$)""")

_DENY_PATTERNS = [
    (
        # `\s\+\S` catches a leading-+ refspec (git push origin +main / +HEAD:main),
        # which forces just like --force; a + mid-token (branch feature/c++) is safe.
        re.compile(r"\bgit\s+push\b.*(?:--force\b(?!-with-lease)|\s-f\b|\s\+\S)", re.IGNORECASE),
        "Bare force-push is blocked (including +refspec); use --force-with-lease.",
    ),
    (
        re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE),
        "git reset --hard is blocked; explain before discarding work.",
    ),
    (re.compile(r"\bsudo\b", re.IGNORECASE), "sudo is blocked."),
    (
        # `(?:\S*/)?` lets an absolute path to the shell (| /bin/sh, | /usr/bin/bash)
        # be caught too, not only a bare `sh`/`bash`; sudo|env covers env-launched shells.
        re.compile(
            r"\b(?:curl|wget)\b[^|]*\|\s*(?:(?:sudo|env)\s+)?(?:\S*/)?(?:ba)?sh\b", re.IGNORECASE
        ),
        "Piping a remote download into a shell is blocked.",
    ),
]

# Match the project's own key formats (sk-proj-, sk-ant-) plus GitHub/AWS keys and
# private-key headers. Kept in sync with post_tool_failure._SECRET.
_SECRET_VALUE = re.compile(
    r"sk-[A-Za-z0-9_-]{16,}"
    r"|gh[pousr]_[A-Za-z0-9]{36,}"
    r"|github_pat_[A-Za-z0-9_]{40,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN[A-Z ]*PRIVATE KEY-----(?:[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----)?"
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
    if not isinstance(payload, dict):
        # A non-object payload carries no Bash command to inspect; fail open quietly.
        return 0
    command = ""
    if payload.get("tool_name") == "Bash":
        tool_input = payload.get("tool_input")
        if isinstance(tool_input, dict):
            raw = tool_input.get("command", "")
            command = raw if isinstance(raw, str) else ""
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
