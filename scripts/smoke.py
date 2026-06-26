"""Deterministic offline smoke: boot the app in-process and exercise /v1/extract.

No network, no paid model calls, no API key. Routing is pinned to the in-process
FixtureClient (LLM_PROVIDER_MODE=fixture + FIXTURE_CANNED_TEXT), so this proves the
full endpoint path (resolve -> client -> validation-retry -> taxonomy) offline:
/healthz is green, a known invoice fixture POSTs to a 200 with the validated record,
and a deliberately-broken canned output forces a 422 validation_failed. The
idempotency replay + 409 assertions land in T12.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "invoices" / "invoice_0001.json"
_FIXTURE_ENV = ("LLM_PROVIDER_MODE", "FIXTURE_CANNED_TEXT")


def _fail(message: str) -> int:
    print(f"SMOKE FAIL: {message}", file=sys.stderr)
    return 1


def _extract_body(fixture: dict[str, object]) -> dict[str, object]:
    return {
        "doc_type": fixture["doc_type"],
        "schema_version": fixture["schema_version"],
        "content": fixture["content"],
        "provider": "openai",  # overridden by LLM_PROVIDER_MODE=fixture; explicit for clarity
    }


def _run_extraction_smoke(client: TestClient) -> int:
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    expected = fixture["expected"]
    os.environ["LLM_PROVIDER_MODE"] = "fixture"

    # 1) Valid canned output -> 200 with the validated record echoed back.
    os.environ["FIXTURE_CANNED_TEXT"] = json.dumps(expected)
    resp = client.post("/v1/extract", json=_extract_body(fixture))
    if resp.status_code != 200:
        return _fail(f"/v1/extract (valid) -> {resp.status_code} {resp.text}")
    data = resp.json()["data"]
    if data != expected:
        return _fail(f"/v1/extract (valid) data mismatch: {data!r} != {expected!r}")

    # 2) Deliberately-broken canned output (total != subtotal + tax) -> forced 422.
    broken = {**expected, "total_minor": int(expected["total_minor"]) + 1}
    os.environ["FIXTURE_CANNED_TEXT"] = json.dumps(broken)
    resp = client.post("/v1/extract", json=_extract_body(fixture))
    if resp.status_code != 422:
        return _fail(f"/v1/extract (broken) -> {resp.status_code}, expected 422")
    if resp.json().get("error") != "validation_failed":
        return _fail(f"/v1/extract (broken) error != validation_failed: {resp.text}")
    return 0


def main() -> int:
    client = TestClient(create_app())
    resp = client.get("/healthz")
    if resp.status_code != 200 or resp.json() != {"status": "ok"}:
        return _fail(f"/healthz -> {resp.status_code} {resp.text}")

    saved = {name: os.environ.get(name) for name in _FIXTURE_ENV}
    try:
        rc = _run_extraction_smoke(client)
    finally:
        # Never leak the fixture routing into the caller's environment.
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    if rc != 0:
        return rc

    print("SMOKE OK: app boots, /healthz green, /v1/extract 200 + forced 422 offline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
