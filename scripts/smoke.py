"""Deterministic offline smoke: boot the app in-process and verify liveness.

No network, no paid model calls. The seeded fixture-provider extraction smoke
(POST a known fixture, assert the validated record + a forced 422 + an
idempotency replay) lands in T04b/T12; for M0 this proves the app boots and
/healthz is green so an agent has a runnable verification surface today.
"""

from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from api.main import create_app


def main() -> int:
    client = TestClient(create_app())
    resp = client.get("/healthz")
    if resp.status_code != 200 or resp.json() != {"status": "ok"}:
        print(f"SMOKE FAIL: /healthz -> {resp.status_code} {resp.text}", file=sys.stderr)
        return 1
    print("SMOKE OK: app boots, /healthz green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
