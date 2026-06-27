"""FastAPI app. POST /v1/extract is the product surface.

The extract flow is: resolve the strict model for (doc_type, schema_version) ->
get the provider client (env-routed) -> run the validation-retry pipeline (provider
call -> strict validate -> one feedback retry) -> render `data` + full `meta`. The
provider seam raises `llm.errors.Provider*` and the pipeline raises `ExtractionFailed`;
this layer maps those onto the `ErrorCode` taxonomy, and `api/errors.py` renders
request-shape errors (validation_failed / unsupported_doc_type) and any unmapped
exception (internal_error) through it too (T05). When an `Idempotency-Key` header is
present, a key + payload-hash match replays the stored response with no model call
(`replayed:true`), and a key reused with a different payload returns
`idempotency_conflict` (409) (T12). `/healthz` stays a trivial liveness probe.
"""

from __future__ import annotations

import os
import time
from typing import Annotated, Any

from fastapi import FastAPI, Header

from api.errors import ErrorCode, ExtractError, install_error_handlers
from api.idempotency import (
    IdempotencyStore,
    SqliteIdempotencyStore,
    StoredResponse,
    payload_hash,
)
from api.models import ExtractMeta, ExtractRequest, ExtractResponse
from llm.client import get_client
from llm.errors import ProviderError, ProviderTimeout
from llm.pipeline import ExtractionFailed, run_extraction
from llm.prompts import build_system_prompt
from schemas.registry import resolve


def _field_confidence(data: dict[str, Any]) -> dict[str, float]:
    """Heuristic per-field confidence: 1.0 for a present value, 0.0 for explicit null.

    This is NOT a calibrated probability (the model emits no per-field score yet); it
    is a presence signal over the validated record. The README and `ExtractMeta` both
    say so. A genuinely-absent field is an explicit null (ADR 0002), so null -> 0.0 is
    the honest reading, not a low-quality extraction.
    """
    return {key: (0.0 if value is None else 1.0) for key, value in data.items()}


def _run_extract(request: ExtractRequest) -> ExtractResponse:
    """Drive one extraction and map provider/validation failures to the taxonomy.

    `resolve` raises `UnknownSchema` (handled -> unsupported_doc_type) for an
    unregistered (doc_type, schema_version). Provider-seam errors and a terminal
    validation failure become the matching `ExtractError`.
    """
    if not request.content.strip():
        # Empty/whitespace content has nothing to extract; fail loud before spending a
        # billed provider call rather than inviting the model to hallucinate a record.
        raise ExtractError(
            ErrorCode.validation_failed,
            detail="content is empty or whitespace-only; nothing to extract",
        )
    model_cls = resolve(request.doc_type, request.schema_version)
    client = get_client(request.provider)
    system = build_system_prompt(request.doc_type)
    try:
        model, result, attempts = run_extraction(
            client, model_cls, system=system, content=request.content
        )
    except ProviderTimeout as exc:
        # Subclass of ProviderError, so it must be caught first to keep its 504 code.
        raise ExtractError(ErrorCode.provider_timeout, detail=str(exc)) from exc
    except ProviderError as exc:
        # Covers ProviderError + ProviderRefusal + ProviderTruncation (all 502 in v1;
        # a dedicated refusal/truncation code is a future taxonomy decision).
        raise ExtractError(ErrorCode.provider_error, detail=str(exc)) from exc
    except ExtractionFailed as exc:
        # Strict validation failed on every attempt: 422 with the full per-attempt
        # trail (JSON-safe by construction) so the caller sees exactly what broke.
        raise ExtractError(
            ErrorCode.validation_failed,
            detail=str(exc),
            extra={"attempts": exc.attempts, "trail": exc.trail},
        ) from exc

    data = model.model_dump(mode="json")
    meta = ExtractMeta(
        provider=client.provider,
        model=result.model,
        schema_version=request.schema_version,
        attempts=attempts,
        field_confidence=_field_confidence(data),
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )
    return ExtractResponse(data=data, meta=meta)


def _store_from_env() -> IdempotencyStore:
    """Build the default SQLite idempotency store from env (ADR 0004)."""
    return SqliteIdempotencyStore(
        os.environ.get("IDEMPOTENCY_DB_PATH", "idempotency.sqlite"),
        int(os.environ.get("IDEMPOTENCY_TTL_HOURS", "24")),
    )


def _run_extract_idempotent(
    store: IdempotencyStore, key: str, request: ExtractRequest
) -> ExtractResponse:
    """Idempotent extraction: check the store before any model call.

    The payload hash is over the canonical serialization of the validated request, so
    two byte-different-but-equivalent bodies for the same key still replay. On a key +
    hash match the stored response is replayed (no model call, `replayed:true`); on a key
    reused with a different payload we fail loud with `idempotency_conflict` (409). Only a
    successful 200 is stored, so a transient failure stays retryable under the same key.
    """
    request_hash = payload_hash(request.model_dump_json().encode())
    existing = store.get(key)
    if existing is not None:
        if existing.payload_sha256 != request_hash:
            raise ExtractError(
                ErrorCode.idempotency_conflict,
                detail="Idempotency-Key was reused with a different request payload",
            )
        replayed = ExtractResponse.model_validate_json(existing.response_json)
        replayed.meta.replayed = True
        return replayed
    response = _run_extract(request)
    store.put(
        key,
        StoredResponse(
            payload_sha256=request_hash,
            response_json=response.model_dump_json(),
            status_code=200,
            created_at_epoch=time.time(),
        ),
    )
    return response


def create_app(*, idempotency_store: IdempotencyStore | None = None) -> FastAPI:
    store = idempotency_store if idempotency_store is not None else _store_from_env()
    app = FastAPI(
        title="extract-api",
        version="0.1.0",
        summary="Strict-schema LLM extraction with validation-retry and per-field accuracy.",
    )
    install_error_handlers(app)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # A plain `def` (not async): the provider call is blocking I/O, so Starlette runs
    # it in a threadpool and the event loop is never pinned. The API is synchronous by
    # design (no async job queue).
    @app.post("/v1/extract", response_model=ExtractResponse)
    def extract(
        request: ExtractRequest,
        idempotency_key: Annotated[str | None, Header()] = None,
    ) -> ExtractResponse:
        # Without a key, every request runs; with one, the store is consulted before any
        # model call (replay on match, 409 on a payload mismatch).
        if idempotency_key is None:
            return _run_extract(request)
        return _run_extract_idempotent(store, idempotency_key, request)

    return app


app = create_app()
