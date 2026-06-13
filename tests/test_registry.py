"""Registry resolves known schemas and raises UnknownSchema on a miss."""

import pytest

from schemas.invoice_v1 import InvoiceV1
from schemas.job_posting_v1 import JobPostingV1
from schemas.registry import UnknownSchema, resolve


def test_resolve_known_schemas():
    assert resolve("invoice", "v1") is InvoiceV1
    assert resolve("uk_job_posting", "v1") is JobPostingV1


def test_resolve_unknown_doc_type_raises():
    with pytest.raises(UnknownSchema):
        resolve("passport", "v1")


def test_resolve_unknown_version_raises():
    with pytest.raises(UnknownSchema):
        resolve("invoice", "v2")
