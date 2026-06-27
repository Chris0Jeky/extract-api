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


def test_multipage_text_is_joined():
    # The all-pages join is the reason _pdf_text iterates; lock it so a page-0-only
    # regression (which is byte-identical on single-page fixtures) is caught.
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "PAGE ONE alpha")
    doc.new_page().insert_text((72, 72), "PAGE TWO beta")
    raw = doc.tobytes()
    doc.close()
    out = extract_pdf_text(base64.b64encode(raw).decode())
    assert "PAGE ONE alpha" in out
    assert "PAGE TWO beta" in out


def test_too_many_pages_fails_loud(monkeypatch):
    monkeypatch.setattr("api.content._MAX_PDF_PAGES", 1)
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "p1")
    doc.new_page().insert_text((72, 72), "p2")
    raw = doc.tobytes()
    doc.close()
    with pytest.raises(ExtractError) as exc:
        extract_pdf_text(base64.b64encode(raw).decode())
    assert exc.value.code.value == "validation_failed"
    assert "page" in exc.value.detail.lower()


def test_oversized_extracted_text_fails_loud(monkeypatch):
    # A small PDF that expands past the text cap (a bomb) fails loud, not OOM.
    monkeypatch.setattr("api.content._MAX_TEXT_CHARS", 3)
    with pytest.raises(ExtractError) as exc:
        extract_pdf_text(_pdf_b64("this text is much longer than three characters"))
    assert exc.value.code.value == "validation_failed"
    assert "char" in exc.value.detail.lower()


def test_line_wrapped_base64_is_accepted():
    # Standard MIME / RFC-2045 base64 wraps at 76 cols with newlines; it must still decode.
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Wrapped base64 invoice")
    raw = doc.tobytes()
    doc.close()
    wrapped = base64.encodebytes(raw).decode()
    assert "\n" in wrapped  # genuinely line-wrapped
    assert "Wrapped base64 invoice" in extract_pdf_text(wrapped)
