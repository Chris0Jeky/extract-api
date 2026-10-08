"""FastAPI app. POST /v1/extract is the product surface.

The extract flow is: resolve the content (text, or a base64 PDF's text via PyMuPDF) ->
resolve the strict model for (doc_type, schema_version) -> get the provider client
(env-routed) -> run the validation-retry pipeline (provider call -> strict validate ->
one feedback retry) -> render `data` + full `meta`. The
provider seam raises `llm.errors.Provider*` and the pipeline raises `ExtractionFailed`;
this layer maps those onto the `ErrorCode` taxonomy, and `api/errors.py` renders
request-shape errors (validation_failed / unsupported_doc_type) and any unmapped
exception (internal_error) through it too (T05). When an `Idempotency-Key` header is
present, a key + payload-hash match replays the stored response with no model call
(`replayed:true`), and a key reused with a different payload returns
`idempotency_conflict` (409) (T12). `/healthz` stays a trivial liveness probe; `/readyz` is
the platform health check (ADR 0005): it proves the idempotency store can write and reports
the image revision and provider mode, so a deploy with a broken disk never goes live.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Annotated, Any

import anyio
import anyio.to_thread
from fastapi import FastAPI, Header, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from api.budget import BudgetGuard, budget_from_env
from api.content import resolve_content
from api.errors import ErrorCode, ExtractError, install_error_handlers
from api.idempotency import (
    EphemeralStoreError,
    IdempotencyStore,
    SqliteIdempotencyStore,
    StoredResponse,
    payload_hash,
)
from api.models import ExtractMeta, ExtractRequest, ExtractResponse
from api.observability import (
    RequestContextMiddleware,
    configure_logging,
    logging_configured,
    note,
    note_client,
    note_meta,
    note_request,
    note_retry,
)
from llm.client import get_client
from llm.errors import ProviderError, ProviderTimeout
from llm.pipeline import ExtractionFailed, run_extraction
from llm.prompts import build_system_prompt
from schemas.registry import resolve

logger = logging.getLogger("extract.api")


def _field_confidence(data: dict[str, Any]) -> dict[str, float]:
    """Heuristic per-field confidence: 1.0 for a present value, 0.0 for explicit null.

    This is NOT a calibrated probability (the model emits no per-field score yet); it
    is a presence signal over the validated record. The README and `ExtractMeta` both
    say so. A genuinely-absent field is an explicit null (ADR 0002), so null -> 0.0 is
    the honest reading, not a low-quality extraction.
    """
    return {key: (0.0 if value is None else 1.0) for key, value in data.items()}


def _bounded(detail: str) -> str:
    """Provider error text for the log: one line, capped.

    Logged on purpose (#21: clients get a sanitized message, operators the detail). It is
    upstream text, so it is the one place a provider echo of the prompt could surface;
    cap it so a pathological echo cannot dump a document.
    """
    return " ".join(detail.split())[:300]


def _run_extract(request: ExtractRequest, budget: BudgetGuard) -> ExtractResponse:
    """Drive one extraction and map provider/validation failures to the taxonomy.

    `resolve` raises `UnknownSchema` (handled -> unsupported_doc_type) for an
    unregistered (doc_type, schema_version). Provider-seam errors and a terminal
    validation failure become the matching `ExtractError`. The per-run budget is checked
    before the (billed) provider call and reconciled with the actual cost after.
    """
    # Resolve the schema first: an unsupported (doc_type, schema_version) fails cheaply and
    # consistently (unsupported_doc_type) before any PDF extraction, which is independent of it.
    model_cls = resolve(request.doc_type, request.schema_version)
    # Resolve the text to extract from: passthrough for text, decoded text for a PDF.
    # A bad PDF (corrupt/oversized/no-text) fails loud here as validation_failed.
    content = resolve_content(request)
    if not content.strip():
        # Empty/whitespace content has nothing to extract; fail loud before spending a
        # billed provider call rather than inviting the model to hallucinate a record.
        raise ExtractError(
            ErrorCode.validation_failed,
            detail="content is empty or whitespace-only; nothing to extract",
        )
    # Enforce the per-run USD budget before spending on the provider call (no-op if disabled).
    budget.check()
    client = get_client(request.provider)
    note_client(client)
    system = build_system_prompt(request.doc_type)
    try:
        model, result, attempts = run_extraction(
            client, model_cls, system=system, content=content, on_retry=note_retry
        )
    except ProviderTimeout as exc:
        # Subclass of ProviderError, so it must be caught first to keep its 504 code. Log the
        # full provider detail server-side but return a sanitized client message, so an
        # upstream provider/gateway error string is never echoed to external callers (#21).
        # Reconcile any spend incurred before the failure so the budget cannot be defeated.
        budget.add(exc.cost_usd)
        note(cost_usd=exc.cost_usd)
        logger.warning("provider timeout (%s): %s", exc.provider, _bounded(exc.detail))
        raise ExtractError(
            ErrorCode.provider_timeout, detail=f"the {exc.provider} provider timed out"
        ) from exc
    except ProviderError as exc:
        # Covers ProviderError + ProviderRefusal + ProviderTruncation (all 502 in v1; a
        # dedicated refusal/truncation code is a future taxonomy decision). Same sanitization:
        # the provider's raw message is logged, not returned in the body.
        budget.add(exc.cost_usd)
        note(cost_usd=exc.cost_usd)
        logger.warning("provider error (%s): %s", exc.provider, _bounded(exc.detail))
        raise ExtractError(
            ErrorCode.provider_error, detail=f"the {exc.provider} provider call failed"
        ) from exc
    except ExtractionFailed as exc:
        # Strict validation failed on every attempt: 422 with the full per-attempt trail
        # (JSON-safe by construction) so the caller sees exactly what broke. The attempts
        # were billed, so reconcile their cost into the budget (a failure-heavy stream must
        # still count against the cap).
        budget.add(exc.cost_usd)
        note(attempts=exc.attempts, cost_usd=exc.cost_usd)
        raise ExtractError(
            ErrorCode.validation_failed,
            detail=str(exc),
            extra={"attempts": exc.attempts, "trail": exc.trail},
        ) from exc

    # Reconcile the request's actual spend (across all attempts) into the running budget.
    budget.add(result.cost_usd)
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


# Idempotency-Key is a client-supplied string used as the store primary key; bound its
# length so a caller cannot store unbounded keys (255 is the common cap, e.g. Stripe).
_MAX_IDEMPOTENCY_KEY_LEN = 255


def _store_from_env() -> IdempotencyStore:
    """Build the default SQLite idempotency store from env (ADR 0004)."""
    raw_require = os.environ.get("IDEMPOTENCY_REQUIRE_PERSISTENT_MOUNT", "0")
    if raw_require not in {"0", "1"}:
        raise ValueError(f"env IDEMPOTENCY_REQUIRE_PERSISTENT_MOUNT={raw_require!r} must be 0 or 1")
    return SqliteIdempotencyStore(
        os.environ.get("IDEMPOTENCY_DB_PATH", "idempotency.sqlite"),
        int(os.environ.get("IDEMPOTENCY_TTL_HOURS", "24")),
        require_persistent_mount=raw_require == "1",
    )


def _validate_idempotency_key(idempotency_key: str) -> str:
    """Normalize + validate a client-supplied Idempotency-Key, failing loud on a bad one.

    A present-but-blank header (`Idempotency-Key:` with no value) is not None, so without
    this it would be used verbatim as a degenerate shared key (cross-request false 409s and
    unintended replays). Fail loud instead, mirroring the empty-content guard, and bound the
    length. Surrounding whitespace is stripped so trivially-different keys do not diverge.
    """
    key = idempotency_key.strip()
    if not key:
        raise ExtractError(ErrorCode.validation_failed, detail="Idempotency-Key must not be blank")
    if len(key) > _MAX_IDEMPOTENCY_KEY_LEN:
        raise ExtractError(
            ErrorCode.validation_failed,
            detail=f"Idempotency-Key must be at most {_MAX_IDEMPOTENCY_KEY_LEN} characters",
        )
    return key


def _run_extract_idempotent(
    store: IdempotencyStore, key: str, request: ExtractRequest, budget: BudgetGuard
) -> ExtractResponse:
    """Idempotent extraction: check the store before any model call.

    The payload hash is over the canonical serialization of the validated request, so
    two byte-different-but-equivalent bodies for the same key still replay. On a key +
    hash match the stored response is replayed (no model call, `replayed:true`); on a key
    reused with a different payload we fail loud with `idempotency_conflict` (409). Only a
    successful 200 is stored, so a transient failure stays retryable under the same key.

    This guarantee is for SEQUENTIAL requests. Concurrent same-key requests can both miss
    `get` and both run before either `put`s (the model call sits in the get/put window);
    atomic reservation for that case is tracked in issue #42.
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
    response = _run_extract(request, budget)
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


def _max_concurrency_from_env() -> int:
    raw = os.environ.get("EXTRACT_MAX_CONCURRENCY", "4")
    if not raw.isascii() or not raw.isdecimal() or int(raw) <= 0:
        raise ValueError(f"EXTRACT_MAX_CONCURRENCY must be a positive integer; got {raw!r}")
    return int(raw)


class ExtractAdmission:
    """Admit at most `limit` /v1/extract requests at once, before their bodies are read.

    Memory, not CPU, bounds an instance (docs/ops/SIZING.md): each in-flight extraction holds
    its body, the decoded PDF and its text. Waiting here, ahead of FastAPI, a queued request
    has not read its body: the server's flow control pauses the socket, so a queue of large
    PDFs costs connections, not memory. Excess requests wait (bounded by the platform's
    request timeout) instead of being shed, so no new error code is needed, and every other
    route, including the health probes, bypasses the gate.
    """

    def __init__(self, app: ASGIApp, *, limit: int) -> None:
        self.app = app
        self.limiter = anyio.CapacityLimiter(limit)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == "/v1/extract":
            async with self.limiter:
                await self.app(scope, receive, send)
        else:
            await self.app(scope, receive, send)


def create_app(
    *, idempotency_store: IdempotencyStore | None = None, budget: BudgetGuard | None = None
) -> FastAPI:
    # The default store is built lazily on first use, so merely importing this module (or
    # serving requests that never use idempotency) performs no filesystem I/O. An injected
    # store / budget (tests, smoke) is used as-is; otherwise both come from env.
    cached_store: IdempotencyStore | None = idempotency_store
    budget_guard = budget if budget is not None else budget_from_env()

    def _store() -> IdempotencyStore:
        nonlocal cached_store
        if cached_store is None:
            cached_store = _store_from_env()
        return cached_store

    app = FastAPI(
        title="extract-api",
        version="0.1.0",
        summary="Strict-schema LLM extraction with validation-retry and per-field accuracy.",
    )
    install_error_handlers(app)
    if not logging_configured():
        configure_logging()
    # The last added is outermost: the request context wraps the admission gate, so a queued
    # extract carries its request id and its access line's duration_ms includes the wait.
    app.add_middleware(ExtractAdmission, limit=_max_concurrency_from_env())
    app.add_middleware(RequestContextMiddleware)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # The probe gets its own one-token limiter instead of the default threadpool, so a
    # saturated extraction pool (every worker waiting on a provider) cannot queue the platform
    # health check behind it and get a healthy-but-busy instance restarted.
    probe_limiter = anyio.CapacityLimiter(1)

    @app.get("/readyz")
    async def readyz() -> dict[str, str]:
        def probe() -> str:
            store = _store()
            store.probe()
            return store.store_id

        try:
            store_id = await anyio.to_thread.run_sync(probe, limiter=probe_limiter)
        except EphemeralStoreError as exc:
            logger.error("readiness probe failed: %s", exc)
            raise ExtractError(
                ErrorCode.internal_error,
                detail="the idempotency store is not on a persistent mount",
            ) from exc
        except Exception as exc:
            # Unready is an internal fault, so it renders as internal_error (500) like any
            # other: no new taxonomy member. The client body stays generic; the log names it.
            logger.error(
                "readiness probe failed: idempotency store: %s: %s", type(exc).__name__, exc
            )
            raise ExtractError(
                ErrorCode.internal_error, detail="the idempotency store is not ready"
            ) from exc
        return {
            "status": "ready",
            "revision": os.environ.get("EXTRACT_API_REVISION") or "unknown",
            "idempotency_store_id": store_id,
            "provider_mode": (
                "fixture" if os.environ.get("LLM_PROVIDER_MODE") == "fixture" else "live"
            ),
        }

    # A plain `def` (not async): the provider call is blocking I/O, so Starlette runs
    # it in a threadpool and the event loop is never pinned. The API is synchronous by
    # design (no async job queue).
    @app.post("/v1/extract", response_model=ExtractResponse)
    def extract(
        request: ExtractRequest,
        response: Response,
        idempotency_key: Annotated[str | None, Header()] = None,
    ) -> ExtractResponse:
        # Without a key, every request runs; with one, the store is consulted before any
        # model call (replay on match, 409 on a payload mismatch).
        note_request(request, keyed=idempotency_key is not None)
        if idempotency_key is None:
            result = _run_extract(request, budget_guard)
        else:
            key = _validate_idempotency_key(idempotency_key)
            store = _store()
            # Name the store that answered, so a client retrying a key can see when the retry
            # reached a different store (a second replica or a replaced disk) and was not replayed.
            response.headers["X-Idempotency-Store"] = store.store_id
            result = _run_extract_idempotent(store, key, request, budget_guard)
        note_meta(result.meta)
        return result

    return app


app = create_app()
