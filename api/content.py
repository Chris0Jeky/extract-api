"""Resolve request content to the text the extraction pipeline consumes.

`content_format="text"` passes the content through unchanged. `content_format="pdf_base64"`
decodes a base64 PDF and extracts its embedded text via PyMuPDF. OCR is a non-goal, so a
scanned/image PDF (no extractable text) fails loud rather than yielding an empty record.
Every malformed-input case (bad base64, oversized, corrupt/non-PDF, no text) raises
`validation_failed` so the client gets a clear 422, never a 500 or a silent empty extract.
"""

from __future__ import annotations

import base64
import binascii

import pymupdf

from api.errors import ErrorCode, ExtractError
from api.models import ExtractRequest

# Oversized guard: a synchronous request must not buffer/parse an unbounded PDF. 10 MiB
# covers real invoices / job postings with margin; bump this constant if a real case needs it.
_MAX_PDF_BYTES = 10 * 1024 * 1024


def resolve_content(request: ExtractRequest) -> str:
    """Return the text to extract from: passthrough for text, decoded text for a PDF."""
    if request.content_format == "text":
        return request.content
    return extract_pdf_text(request.content)


def extract_pdf_text(content_b64: str) -> str:
    """Decode a base64 PDF and return its embedded text, failing loud on bad input."""
    try:
        raw = base64.b64decode(content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ExtractError(
            ErrorCode.validation_failed, detail="content is not valid base64 (pdf_base64)"
        ) from exc
    if len(raw) > _MAX_PDF_BYTES:
        raise ExtractError(
            ErrorCode.validation_failed,
            detail=f"PDF exceeds the {_MAX_PDF_BYTES // (1024 * 1024)} MiB limit",
        )
    text = _pdf_text(raw)
    if not text.strip():
        raise ExtractError(
            ErrorCode.validation_failed,
            detail="PDF has no extractable text (scanned/image PDFs need OCR, a non-goal)",
        )
    return text


def _pdf_text(raw: bytes) -> str:
    # Any failure to open or read the supplied bytes is a malformed-input problem (corrupt
    # or non-PDF, e.g. PyMuPDF's FileDataError), not a server fault: map every such failure
    # to validation_failed rather than letting it escape to a 500.
    try:
        with pymupdf.open(stream=raw, filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc)
    except Exception as exc:
        raise ExtractError(
            ErrorCode.validation_failed, detail="content is not a readable PDF"
        ) from exc
