"""Tests for the agent safety hooks' redaction and main() entrypoints.

The hooks live under scripts/ (run standalone, not packaged), so load them by path.
smoke_test.py already covers decide() over the deny/allow corpus; this adds the
secret-redaction breadth (modern key formats) and drives the main() entrypoints,
which were previously untested and excluded from coverage.
"""

import importlib.util
import io
import json
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent.parent / "scripts" / "agent_hooks"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _HOOKS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pre = _load("pre_tool_use")
post = _load("post_tool_failure")

MODERN_SECRETS = [
    "sk-proj-AbCdEf0123456789AbCdEf0123",
    "sk-ant-api03-AbCdEf0123456789AbCdEf0123456789",
    "ghp_0123456789abcdefABCDEF0123456789abcd",
    "sk-ABCDEF0123456789ABCD",  # legacy form must still redact
    "AKIA0123456789ABCDEF",
]


def test_redact_covers_modern_key_formats():
    for secret in MODERN_SECRETS:
        redacted = post._redact(f"auth failed token={secret} end")
        assert secret not in redacted, f"leaked: {secret}"
        assert "[REDACTED]" in redacted


def test_redact_leaves_innocuous_text():
    assert post._redact("just a normal log line") == "just a normal log line"


def test_pre_decide_denies_modern_key_write():
    decision, _ = pre.decide("echo sk-proj-AbCdEf0123456789AbCd > keys.txt")
    assert decision == "deny"


def test_pre_main_non_dict_payload_is_silent(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("[1, 2, 3]"))
    assert pre.main() == 0
    assert capsys.readouterr().out == ""


def test_pre_main_emits_deny_for_dangerous_command(monkeypatch, capsys):
    payload = {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert pre.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_pre_main_allows_safe_command_silently(monkeypatch, capsys):
    payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert pre.main() == 0
    assert capsys.readouterr().out == ""


def test_post_main_redacts_secret_into_ledger(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    secret = "sk-ant-api03-AbCdEf0123456789AbCdEf0123456789"
    payload = {"tool_name": "Bash", "tool_response": {"stderr": f"auth error {secret}"}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert post.main() == 0
    ledger = tmp_path / ".claude" / "local" / "failure_ledger.jsonl"
    content = ledger.read_text(encoding="utf-8")
    assert secret not in content
    assert "[REDACTED]" in content


def test_post_main_ignores_non_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    payload = {"tool_name": "Bash", "tool_response": {"stdout": "all good"}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert post.main() == 0
    assert not (tmp_path / ".claude" / "local" / "failure_ledger.jsonl").exists()
