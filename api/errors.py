"""Error taxonomy: every non-200 carries exactly one ErrorCode.

This module is import-safe: it imports no provider SDK and no heavy logic, so the
schema layer can map onto it freely.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from schemas.registry import UnknownSchema

logger = logging.getLogger("extract.api")


class ErrorCode(StrEnum):
    validation_failed = "validation_failed"
    low_confidence = "low_confidence"
    unsupported_doc_type = "unsupported_doc_type"
    provider_error = "provider_error"
    provider_timeout = "provider_timeout"
    budget_exceeded = "budget_exceeded"
    idempotency_conflict = "idempotency_conflict"
    # Catch-all for any otherwise-unmapped exception, so every non-200 still carries
    # exactly one code (the only 500 in the taxonomy). Added in T05.
    internal_error = "internal_error"


# Exactly one HTTP status per taxonomy member.
STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.validation_failed: 422,
    ErrorCode.low_confidence: 422,
    ErrorCode.unsupported_doc_type: 422,
    ErrorCode.provider_error: 502,
    ErrorCode.provider_timeout: 504,
    ErrorCode.budget_exceeded: 402,
    ErrorCode.idempotency_conflict: 409,
    ErrorCode.internal_error: 500,
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
        # `extra` is supplementary context only. The taxonomy code (and detail) are
        # authoritative and must always win, so strip any reserved keys from extra
        # before stamping them: every non-200 carries exactly one correct ErrorCode.
        body: dict[str, object] = {
            k: v for k, v in self.extra.items() if k not in {"error", "detail"}
        }
        body["error"] = self.code.value
        if self.detail:
            body["detail"] = self.detail
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

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Render request-shape errors through the taxonomy instead of FastAPI's default
        # 422 body (closes #5). Only a genuinely out-of-Literal doc_type VALUE is
        # unsupported_doc_type; a missing/empty/otherwise-malformed body (including an
        # omitted doc_type) is validation_failed. Gate on the literal-mismatch kind so a
        # forgotten doc_type is not mislabeled as "unsupported", and anchor on the field
        # position so only an error ON doc_type qualifies. doc_type classification wins
        # over any coexisting field error.
        code = ErrorCode.validation_failed
        for err in exc.errors():
            # Defensive: pydantic always emits loc as a tuple, but guard the subscript so a
            # malformed/None loc cannot raise inside the handler.
            loc = err.get("loc")
            if (
                loc
                and isinstance(loc, (tuple, list))
                and loc[-1] == "doc_type"
                and err.get("type") == "literal_error"
            ):
                code = ErrorCode.unsupported_doc_type
                break
        detail = (
            "unsupported doc_type"
            if code is ErrorCode.unsupported_doc_type
            else "request validation failed"
        )
        return error_response(code, {"error": code.value, "detail": detail})

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Any otherwise-unmapped exception still carries exactly one ErrorCode. The full
        # error is logged server-side; the client gets a generic detail (no internal leak).
        logger.exception("unhandled exception during request: %s", type(exc).__name__)
        return error_response(
            ErrorCode.internal_error,
            {"error": ErrorCode.internal_error.value, "detail": "internal error"},
        )
