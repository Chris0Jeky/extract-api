"""Error taxonomy: one status per code, and handlers render the taxonomy body."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.errors import (
    STATUS_BY_CODE,
    ErrorCode,
    ExtractError,
    error_response,
    install_error_handlers,
)
from schemas.registry import UnknownSchema


def test_every_code_has_exactly_one_status():
    for code in ErrorCode:
        assert code in STATUS_BY_CODE
    assert STATUS_BY_CODE[ErrorCode.idempotency_conflict] == 409
    assert STATUS_BY_CODE[ErrorCode.validation_failed] == 422
    assert STATUS_BY_CODE[ErrorCode.internal_error] == 500


@pytest.mark.parametrize("code", list(ErrorCode))
def test_every_code_renders_its_status_and_body(code):
    # Each taxonomy member renders to its one HTTP status WITH its code in the body
    # (covers low_confidence and budget_exceeded, which no live path raises yet).
    resp = error_response(code, {"error": code.value, "detail": "x"})
    assert resp.status_code == STATUS_BY_CODE[code]
    assert json.loads(resp.body)["error"] == code.value


# Every taxonomy code is either reachable via a live request path or reserved for an
# unbuilt feature. Each live-reachable code below is produced end-to-end by a real request
# elsewhere: validation_failed / unsupported_doc_type / provider_error / provider_timeout /
# idempotency_conflict / internal_error in tests/test_extract_endpoint.py; not_found /
# method_not_allowed in tests/test_api.py.
_RESERVED_CODES = {
    ErrorCode.low_confidence,  # needs confidence-gating (not built)
    ErrorCode.budget_exceeded,  # needs the budget guard (M3 / T18)
}
_LIVE_REACHABLE_CODES = {
    ErrorCode.validation_failed,
    ErrorCode.unsupported_doc_type,
    ErrorCode.provider_error,
    ErrorCode.provider_timeout,
    ErrorCode.idempotency_conflict,
    ErrorCode.internal_error,
    ErrorCode.not_found,
    ErrorCode.method_not_allowed,
}


def test_every_code_is_reachable_or_reserved():
    # Tripwire: adding a new ErrorCode fails this until it is classified as live-reachable
    # (with an end-to-end test) or reserved, so the taxonomy cannot silently grow an
    # unreachable/untested member (CLAUDE.md: new members need owner approval).
    assert _LIVE_REACHABLE_CODES.isdisjoint(_RESERVED_CODES)
    assert set(ErrorCode) == _LIVE_REACHABLE_CODES | _RESERVED_CODES


def test_extract_error_body_carries_one_code():
    err = ExtractError(ErrorCode.validation_failed, detail="bad", extra={"attempts": 2})
    body = err.to_body()
    assert body["error"] == "validation_failed"
    assert body["detail"] == "bad"
    assert body["attempts"] == 2


def test_extra_cannot_override_taxonomy_code():
    # A caller-supplied extra dict must never clobber the authoritative code/detail.
    err = ExtractError(
        ErrorCode.validation_failed,
        detail="real detail",
        extra={"error": "totally_wrong", "detail": "clobbered", "attempts": 2},
    )
    body = err.to_body()
    assert body["error"] == "validation_failed"
    assert body["detail"] == "real detail"
    assert body["attempts"] == 2


def test_error_response_status():
    resp = error_response(ErrorCode.provider_timeout, {"error": "provider_timeout"})
    assert resp.status_code == 504


def test_handlers_render_taxonomy():
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    async def boom() -> dict[str, str]:
        raise ExtractError(ErrorCode.budget_exceeded, detail="cap reached")

    @app.get("/unknown")
    async def unknown() -> dict[str, str]:
        raise UnknownSchema("no schema")

    @app.get("/explode")
    async def explode() -> dict[str, str]:
        # An unmapped exception must still render the taxonomy (internal_error), never a
        # bare 500. The catch-all also logs the real error server-side (not asserted here).
        raise RuntimeError("unexpected boom")

    @app.get("/teapot")
    async def teapot() -> dict[str, str]:
        # An HTTPException at a status the taxonomy has no code for (not 404/405) degrades
        # to internal_error WITHOUT leaking exc.detail.
        raise StarletteHTTPException(status_code=403, detail="forbidden token=SECRET")

    client = TestClient(app, raise_server_exceptions=False)

    r1 = client.get("/boom")
    assert r1.status_code == 402
    assert r1.json()["error"] == "budget_exceeded"

    r2 = client.get("/unknown")
    assert r2.status_code == 422
    assert r2.json()["error"] == "unsupported_doc_type"

    r3 = client.get("/explode")
    assert r3.status_code == 500
    assert r3.json()["error"] == "internal_error"
    assert r3.json()["detail"] == "internal error"  # generic; no internal leak

    r4 = client.get("/teapot")
    assert r4.status_code == 500
    assert r4.json()["error"] == "internal_error"
    assert "SECRET" not in r4.text  # the original HTTPException detail is not echoed
