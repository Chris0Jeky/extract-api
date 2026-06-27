"""Deterministic offline smoke: boot the app in-process and exercise /v1/extract.

No network, no paid model calls, no API key. Routing is pinned to the in-process
FixtureClient (LLM_PROVIDER_MODE=fixture + FIXTURE_CANNED_TEXT), so this proves the
full endpoint path (resolve -> client -> validation-retry -> taxonomy) offline:
/healthz is green, a known invoice fixture POSTs to a 200 with the validated record,
and a deliberately-broken canned output forces a 422 validation_failed. It also
exercises idempotency: a key + payload match replays (replayed:true, no model call)
and the same key with a different payload returns 409 idempotency_conflict.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from api.idempotency import SqliteIdempotencyStore
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


def _run_idempotency_smoke(client: TestClient) -> int:
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    expected = fixture["expected"]
    body = _extract_body(fixture)
    headers = {"Idempotency-Key": "smoke-key-1"}
    os.environ["LLM_PROVIDER_MODE"] = "fixture"
    os.environ["FIXTURE_CANNED_TEXT"] = json.dumps(expected)

    # 1) First call with a key -> real (fixture) extraction, not a replay.
    first = client.post("/v1/extract", json=body, headers=headers)
    if first.status_code != 200:
        return _fail(f"/v1/extract (idempotent first) -> {first.status_code} {first.text}")
    if first.json()["meta"]["replayed"] is not False:
        return _fail("/v1/extract (idempotent first) should not be a replay")

    # 2) Replay: same key + payload. Clear the canned text first, so a real model call would
    #    now fail loud; a 200 with replayed:true proves no model call happened.
    os.environ["FIXTURE_CANNED_TEXT"] = ""
    replay = client.post("/v1/extract", json=body, headers=headers)
    if replay.status_code != 200:
        return _fail(f"/v1/extract (replay) -> {replay.status_code} {replay.text}")
    if replay.json()["meta"]["replayed"] is not True:
        return _fail("/v1/extract (replay) should set replayed:true")
    if replay.json()["data"] != expected:
        return _fail("/v1/extract (replay) data mismatch")

    # 3) Conflict: same key + a different payload -> 409, before any model call.
    conflict_body = {**body, "content": str(body["content"]) + " (changed)"}
    conflict = client.post("/v1/extract", json=conflict_body, headers=headers)
    if conflict.status_code != 409:
        return _fail(f"/v1/extract (conflict) -> {conflict.status_code}, expected 409")
    if conflict.json().get("error") != "idempotency_conflict":
        return _fail(f"/v1/extract (conflict) error != idempotency_conflict: {conflict.text}")
    return 0


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        # Inject a throwaway store so the smoke never touches a real idempotency db.
        store = SqliteIdempotencyStore(str(Path(tmp) / "smoke_idem.sqlite"))
        client = TestClient(create_app(idempotency_store=store))
        resp = client.get("/healthz")
        if resp.status_code != 200 or resp.json() != {"status": "ok"}:
            return _fail(f"/healthz -> {resp.status_code} {resp.text}")

        saved = {name: os.environ.get(name) for name in _FIXTURE_ENV}
        try:
            rc = _run_extraction_smoke(client)
            if rc == 0:
                rc = _run_idempotency_smoke(client)
        finally:
            # Never leak the fixture routing into the caller's environment.
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        if rc != 0:
            return rc

    print(
        "SMOKE OK: app boots, /healthz green, /v1/extract 200 + forced 422, "
        "idempotency replay + 409, offline"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
