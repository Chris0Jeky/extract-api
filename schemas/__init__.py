"""Strict, versioned extraction schemas, registered by (doc_type, schema_version)."""

from schemas.invoice_v1 import InvoiceV1, LineItem
from schemas.job_posting_v1 import JobPostingV1
from schemas.registry import REGISTRY, UnknownSchema, resolve

__all__ = [
    "REGISTRY",
    "InvoiceV1",
    "JobPostingV1",
    "LineItem",
    "UnknownSchema",
    "resolve",
]
