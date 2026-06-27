"""Request and response models for POST /v1/extract.

These are the API boundary (not the strict extraction schemas). They forbid
unknown request keys but otherwise use FastAPI's normal body parsing.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_type: Literal["invoice", "uk_job_posting"]
    schema_version: str = "v1"
    content: str
    # "text": content is the document text. "pdf_base64": content is a base64-encoded PDF
    # whose embedded text is extracted server-side (PyMuPDF, no OCR). Defaults to text, so
    # existing callers are unaffected.
    content_format: Literal["text", "pdf_base64"] = "text"
    provider: Literal["openai", "anthropic", "default"] = "default"


class ExtractMeta(BaseModel):
    provider: str
    model: str
    schema_version: str
    attempts: int
    replayed: bool = False
    # field_confidence is HEURISTIC (presence + validation pass + optional model
    # self-report). It is not a calibrated probability; the README says so.
    field_confidence: dict[str, float]
    cost_usd: float
    latency_ms: float


class ExtractResponse(BaseModel):
    data: dict[str, Any]
    meta: ExtractMeta
