"""System prompts for extraction.

The seam is text-based (ADR 0002): the model returns a JSON object as text that the
validation-retry pipeline strict-validates. The system prompt restates the
normalization contract the strict schema enforces after parse (explicit null for
absent fields, ISO-8601 dates, integer minor units, ISO-4217 currency) so the model
is steered toward output that validates on the first attempt. The JSON schema itself
is sent separately by the client; this prompt is supplementary guidance, never the
sole source of shape.
"""

from __future__ import annotations

# Human-readable labels per supported doc type. An unknown doc_type still gets a
# usable prompt ("a document"); the registry is what authoritatively rejects an
# unsupported type, so the prompt never needs to fail here.
_DOC_LABELS: dict[str, str] = {
    "invoice": "an invoice",
    "uk_job_posting": "a UK job posting",
}

_BASE = (
    "You extract structured data from documents into a strict JSON schema. "
    "Return ONLY a single JSON object that conforms to the provided schema, with no "
    "prose, markdown, or code fences. Rules: use the exact field names from the "
    "schema; include every field, using an explicit null for any value that is "
    "genuinely absent from the document; never guess, infer, or invent a value; "
    "write dates in ISO-8601 (YYYY-MM-DD); write monetary amounts as integer minor "
    "units (for example pence or cents), never decimal strings; write currency as a "
    "3-letter uppercase ISO-4217 code."
)


def build_system_prompt(doc_type: str) -> str:
    """Return the extraction system prompt, tailored by doc type."""
    label = _DOC_LABELS.get(doc_type, "a document")
    return f"{_BASE} The document is {label}."
