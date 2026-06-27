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

# Oversized guards: cap not only the compressed input but the post-parse work, since a small
# PDF can expand to an enormous page count or enormous text (a "PDF bomb"). 10 MiB input,
# 1000 pages, and ~4 MiB of extracted text cover real invoices / job postings with margin.
_MAX_PDF_BYTES = 10 * 1024 * 1024
_MAX_PDF_PAGES = 1000
_MAX_TEXT_CHARS = 4 * 1024 * 1024


def resolve_content(request: ExtractRequest) -> str:
    """Return the text to extract from: passthrough for text, decoded text for a PDF."""
    if request.content_format == "text":
        return request.content
    return extract_pdf_text(request.content)


def extract_pdf_text(content_b64: str) -> str:
    """Decode a base64 PDF and return its embedded text, failing loud on bad input."""
    try:
        # Strip ASCII whitespace first so standard line-wrapped (RFC 2045 / MIME) base64 is
        # accepted; validate=True still rejects genuine non-base64 garbage.
        raw = base64.b64decode("".join(content_b64.split()), validate=True)
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
    # Bound the post-parse work, not just the input: a small PDF can expand to a huge page
    # count or huge text (a bomb). Reject above the page cap and stop accumulating past the
    # text cap, so untrusted bytes cannot exhaust memory/CPU. Any other open/read failure is a
    # malformed-input problem (e.g. PyMuPDF's FileDataError) -> validation_failed, never a 500.
    try:
        with pymupdf.open(stream=raw, filetype="pdf") as doc:
            if doc.page_count > _MAX_PDF_PAGES:
                raise ExtractError(
                    ErrorCode.validation_failed,
                    detail=f"PDF has more than {_MAX_PDF_PAGES} pages",
                )
            parts: list[str] = []
            total = 0
            for page in doc:
                chunk: str = page.get_text()
                total += len(chunk)
                if total > _MAX_TEXT_CHARS:
                    raise ExtractError(
                        ErrorCode.validation_failed,
                        detail=f"PDF extracted text exceeds the {_MAX_TEXT_CHARS}-char limit",
                    )
                parts.append(chunk)
            return "\n".join(parts)
    except ExtractError:
        # Our own loud caps must not be re-wrapped as the generic "not a readable PDF".
        raise
    except Exception as exc:
        raise ExtractError(
            ErrorCode.validation_failed, detail="content is not a readable PDF"
        ) from exc
