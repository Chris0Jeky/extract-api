"""Real uvicorn, default log config: nothing it logs may carry an exception message.

uvicorn's LOGGING_CONFIG gives the parent `uvicorn` logger its own stderr handler with
propagate False, and applies it BEFORE the app module is imported (CLI behaviour, mirrored
here with an import string). Starlette re-raises after the 500 handler, so uvicorn logs
"Exception in ASGI application" with the traceback, message included, unless it is routed
through the redacting JSON handler.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import textwrap
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

CANARY = "CANARY-uvicorn-5b1d-DO-NOT-LOG"
_ROOT = Path(__file__).resolve().parent.parent

_APP = f"""
from api.main import create_app

app = create_app()


@app.get("/boom")
def boom():
    raise RuntimeError("boom {CANARY}")
"""

_RUN = """
import sys, uvicorn
uvicorn.run("boom_app:app", app_dir=sys.argv[1], port=int(sys.argv[2]), access_log={access})
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _get(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return exc.code


@pytest.mark.parametrize("access", [False, True])
def test_uvicorn_default_logging_is_redacted_json(tmp_path, access):
    (tmp_path / "boom_app.py").write_text(textwrap.dedent(_APP), encoding="utf-8")
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-c", _RUN.format(access=access), str(tmp_path), str(port)],
        cwd=_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("COV_CORE")},
    )
    seen: dict[str, list[str]] = {"out": [], "err": []}

    def drain(stream, key):
        for line in stream:
            seen[key].append(line)

    readers = [
        threading.Thread(target=drain, args=(proc.stdout, "out"), daemon=True),
        threading.Thread(target=drain, args=(proc.stderr, "err"), daemon=True),
    ]
    for reader in readers:
        reader.start()
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                if _get(f"{base}/healthz") == 200:
                    break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("uvicorn did not start")
        assert _get(f"{base}/boom?q={CANARY}") == 500
        # uvicorn logs the re-raised exception AFTER the 500 is sent: wait for that line.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not any(
            "Exception in ASGI application" in line for line in seen["out"] + seen["err"]
        ):
            time.sleep(0.1)
    finally:
        proc.terminate()
        proc.wait(timeout=15)
        for reader in readers:
            reader.join(timeout=5)
    combined = "".join(seen["out"] + seen["err"])
    assert CANARY not in combined, combined[-1500:]
    lines = [line for line in combined.splitlines() if line.strip()]
    parsed = []
    for line in lines:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            pytest.fail(f"non-JSON line on stdout/stderr: {line[:200]!r}")
    crash = [p for p in parsed if "Exception in ASGI application" in p["msg"]]
    assert crash and crash[0]["exc_type"] == "RuntimeError", combined[-2500:]
