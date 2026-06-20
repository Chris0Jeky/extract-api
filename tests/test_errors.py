"""Error taxonomy: one status per code, and handlers render the taxonomy body."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

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

    client = TestClient(app, raise_server_exceptions=False)

    r1 = client.get("/boom")
    assert r1.status_code == 402
    assert r1.json()["error"] == "budget_exceeded"

    r2 = client.get("/unknown")
    assert r2.status_code == 422
    assert r2.json()["error"] == "unsupported_doc_type"
