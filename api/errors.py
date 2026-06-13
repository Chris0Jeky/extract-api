"""Error taxonomy: every non-200 carries exactly one ErrorCode.

This module is import-safe: it imports no provider SDK and no heavy logic, so the
schema layer can map onto it freely.
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from schemas.registry import UnknownSchema


class ErrorCode(StrEnum):
    validation_failed = "validation_failed"
    low_confidence = "low_confidence"
    unsupported_doc_type = "unsupported_doc_type"
    provider_error = "provider_error"
    provider_timeout = "provider_timeout"
    budget_exceeded = "budget_exceeded"
    idempotency_conflict = "idempotency_conflict"


# Exactly one HTTP status per taxonomy member.
STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.validation_failed: 422,
    ErrorCode.low_confidence: 422,
    ErrorCode.unsupported_doc_type: 422,
    ErrorCode.provider_error: 502,
    ErrorCode.provider_timeout: 504,
    ErrorCode.budget_exceeded: 402,
    ErrorCode.idempotency_conflict: 409,
}


class ExtractError(Exception):
    """Domain error carrying one taxonomy code plus an optional structured body."""

    def __init__(
        self,
        code: ErrorCode,
        *,
        detail: str = "",
        extra: dict[str, object] | None = None,
    ) -> None:
        super().__init__(detail or code.value)
        self.code = code
        self.detail = detail
        self.extra = extra or {}

    def to_body(self) -> dict[str, object]:
        body: dict[str, object] = {"error": self.code.value}
        if self.detail:
            body["detail"] = self.detail
        body.update(self.extra)
        return body


def error_response(code: ErrorCode, body: dict[str, object]) -> JSONResponse:
    return JSONResponse(status_code=STATUS_BY_CODE[code], content=body)


def install_error_handlers(app: FastAPI) -> None:
    """Register taxonomy-aware handlers so every error body has one ErrorCode."""

    @app.exception_handler(ExtractError)
    async def _handle_extract_error(_: Request, exc: ExtractError) -> JSONResponse:
        return error_response(exc.code, exc.to_body())

    @app.exception_handler(UnknownSchema)
    async def _handle_unknown_schema(_: Request, exc: UnknownSchema) -> JSONResponse:
        return error_response(
            ErrorCode.unsupported_doc_type,
            {"error": ErrorCode.unsupported_doc_type.value, "detail": str(exc)},
        )
