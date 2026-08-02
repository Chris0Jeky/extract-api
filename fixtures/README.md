# Fixtures and labeling rules

Fixtures are the ground truth the accuracy harness scores against. They are data,
not code, and they are only as good as their labels, so the rules below are
strict.

## Counts and sourcing (ADR 0003)

- 30 to 50 fixtures per doc type for the full accuracy run.
- Job postings: 50/50 hand-collected-and-anonymized vs synthetic, each file
  labeled which it is.
- Invoices may lean synthetic (invoice structure is well understood).

## Labeling rules

- **Anonymize all real data.** No real company names, people, emails, tax IDs, or
  addresses. Replace with neutral substitutes; keep the genuine ambiguity.
- **Labels are the normalized expected output:** dates ISO-8601, money integer
  minor units + ISO-4217 currency, a genuinely-absent field is `null` (never a
  guessed value). All schema fields are present (null where absent), mirroring the
  providers' strict structured-output shape.
- **DRAFT vs REVIEWED.** Agent-drafted labels carry `"label_status": "DRAFT"` and
  are NEVER counted in any published number until a human reviews them and flips
  them to `"REVIEWED"`. `make fixtures-validate` validates structure for both; the
  accuracy harness scores only REVIEWED.
- **Hallucinated-field metric:** when the model invents a value for a field whose
  REVIEWED label is `null`, that is a hallucinated field (the most interesting
  column in the accuracy table).

## File format

One JSON file per fixture, under `fixtures/invoices/` or `fixtures/job_postings/`:

```json
{
  "fixture_id": "invoice_0001",
  "doc_type": "invoice",
  "schema_version": "v1",
  "source": "synthetic",
  "label_status": "DRAFT",
  "content": "<the raw document text the model extracts from>",
  "expected": { "...": "normalized expected fields for the registered schema" }
}
```

`make fixtures-validate` checks every file: required keys present, `source` in
{real_anonymized, synthetic}, `label_status` in {DRAFT, REVIEWED}, and the
`expected` label validates against the strict schema for (doc_type,
schema_version).

## Current state

There are 10 REVIEWED invoice fixtures and 0 job-posting fixtures. The
`fixtures/job_postings/` directory contains only `.gitkeep`; new human-reviewed
labels are still needed for future T15 fixtures before they can be scored.

### Total-only invoice convention

For `invoice_0007` and `invoice_0008`, the source states only a total. Because
invoice.v1 cannot represent a null subtotal (#35), these labels set
`subtotal_minor=total_minor`. This is a scoring convention, not an inferred
subtotal, and deliberately differs from a back-calculated ex-VAT subtotal. Do
not infer line items.
