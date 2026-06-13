"""Schema registry: the single place (doc_type, schema_version) resolves to a model.

A lookup miss raises UnknownSchema, which the API layer maps to the
`unsupported_doc_type` taxonomy error. Adding invoice.v2 later is one entry here.
"""

from __future__ import annotations

from pydantic import BaseModel

from schemas.invoice_v1 import InvoiceV1
from schemas.job_posting_v1 import JobPostingV1


class UnknownSchema(LookupError):
    """No model registered for the requested (doc_type, schema_version)."""


REGISTRY: dict[tuple[str, str], type[BaseModel]] = {
    ("invoice", "v1"): InvoiceV1,
    ("uk_job_posting", "v1"): JobPostingV1,
}


def resolve(doc_type: str, schema_version: str) -> type[BaseModel]:
    """Return the model for (doc_type, schema_version) or raise UnknownSchema."""
    try:
        return REGISTRY[(doc_type, schema_version)]
    except KeyError as exc:
        raise UnknownSchema(
            f"no schema registered for (doc_type={doc_type!r}, schema_version={schema_version!r})"
        ) from exc
