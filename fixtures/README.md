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

## Current state (M0)

10 DRAFT invoice fixtures are seeded for Chris to review. They are agent-drafted
and must not be presented as ground truth until cleared to REVIEWED.
