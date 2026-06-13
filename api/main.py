"""FastAPI app. POST /v1/extract is the product surface; it is a stub until M1.

`/healthz` is real so the app boots and `make smoke` can check liveness now. The
extract pipeline (provider call -> strict validate -> retry -> taxonomy) lands in
T02-T04.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Header

from api.errors import install_error_handlers
from api.models import ExtractRequest, ExtractResponse


def create_app() -> FastAPI:
    app = FastAPI(
        title="extract-api",
        version="0.1.0",
        summary="Strict-schema LLM extraction with validation-retry and per-field accuracy.",
    )
    install_error_handlers(app)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/extract", response_model=ExtractResponse)
    async def extract(
        request: ExtractRequest,
        idempotency_key: Annotated[str | None, Header()] = None,
    ) -> ExtractResponse:
        raise NotImplementedError("extract pipeline lands in M1 (T02-T04)")

    return app


app = create_app()
