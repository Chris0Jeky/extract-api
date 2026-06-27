"""PDF content resolution (T14): a base64 PDF -> embedded text via PyMuPDF, failing loud.

PDFs are built in-process with PyMuPDF (no committed binary fixture), so the tests stay
deterministic and offline. No OCR: a text-free PDF fails loud rather than yielding nothing.
"""

from __future__ import annotations

import base64

import pymupdf
import pytest

from api.content import extract_pdf_text, resolve_content
from api.errors import ExtractError
from api.models import ExtractRequest


def _pdf_b64(text: str) -> str:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    raw = doc.tobytes()
    doc.close()
    return base64.b64encode(raw).decode()


def _blank_pdf_b64() -> str:
    doc = pymupdf.open()
    doc.new_page()  # no text inserted
    raw = doc.tobytes()
    doc.close()
    return base64.b64encode(raw).decode()


def test_extract_pdf_text_returns_embedded_text():
    assert "Invoice INV-42 total 100" in extract_pdf_text(_pdf_b64("Invoice INV-42 total 100"))


def test_resolve_content_passes_text_through():
    req = ExtractRequest(doc_type="invoice", content="raw text here")
    assert resolve_content(req) == "raw text here"


def test_resolve_content_extracts_pdf():
    req = ExtractRequest(
        doc_type="invoice", content=_pdf_b64("PDF body text"), content_format="pdf_base64"
    )
    assert "PDF body text" in resolve_content(req)


def test_invalid_base64_fails_loud():
    with pytest.raises(ExtractError) as exc:
        extract_pdf_text("not!!valid!!base64!!")
    assert exc.value.code.value == "validation_failed"
    assert "base64" in exc.value.detail.lower()


def test_non_pdf_bytes_fail_loud():
    not_pdf = base64.b64encode(b"this is plainly not a pdf document").decode()
    with pytest.raises(ExtractError) as exc:
        extract_pdf_text(not_pdf)
    assert exc.value.code.value == "validation_failed"
    assert "pdf" in exc.value.detail.lower()


def test_oversized_pdf_fails_loud(monkeypatch):
    # Shrink the cap so a tiny PDF trips it, rather than building a 10 MiB fixture.
    monkeypatch.setattr("api.content._MAX_PDF_BYTES", 10)
    with pytest.raises(ExtractError) as exc:
        extract_pdf_text(_pdf_b64("anything"))
    assert exc.value.code.value == "validation_failed"
    assert "limit" in exc.value.detail.lower()


def test_text_free_pdf_fails_loud():
    # A blank/scanned PDF has no extractable text; OCR is a non-goal, so fail loud.
    with pytest.raises(ExtractError) as exc:
        extract_pdf_text(_blank_pdf_b64())
    assert exc.value.code.value == "validation_failed"
    assert "ocr" in exc.value.detail.lower()
