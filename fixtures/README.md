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

As of 2026-11-05, there are 10 REVIEWED invoices, 20 DRAFT invoices, and 20 DRAFT
job postings. The new synthetic fixtures reduce T15's authoring work; they do not
complete its human-review or real-document sourcing gates. No job posting is
eligible for published scoring yet. Each new file includes `review_focus` to
identify the labeling decision to check before changing its status.

| Draft files | Review focus |
| --- | --- |
| `invoice_0011` to `invoice_0014` | Fractional quantity, line discount, zero-decimal JPY, three-decimal KWD |
| `invoice_0015` to `invoice_0020` | Total-only convention, unknown versus zero tax, credit signs, itemized shipping, no inferred line items |
| `invoice_0021` to `invoice_0026` | Zero amounts, rounding, informational exchange rates, CHF, BHD, decimal-comma formatting |
| `invoice_0027` to `invoice_0030` | Small values, repeated descriptions, complete optional fields, CAD dollar symbols |
| `job_posting_0001` to `job_posting_0006` | Annual, monthly, daily and hourly salary; competitive pay; sparse text |
| `job_posting_0007` to `job_posting_0012` | One-sided bounds, fixed pay, internship, explicit and ambiguous visa wording |
| `job_posting_0013` to `job_posting_0020` | Non-GBP pay, seniority, conditional sponsorship, bonus exclusions, absent salary period, zero pay, actual part-time pay |

Fixed salary drafts use equal lower and upper bounds. Right-to-work wording alone
and case-by-case sponsorship use `visa_sponsorship: unspecified`; review those
conventions carefully. Every amount is in minor currency units, including job pay.
All names and identifiers in these drafts are invented for the synthetic corpus.

Inverted salary ranges remain negative schema/pipeline test cases. This success
corpus requires a schema-valid expected record, so it cannot honestly label an
invalid range by silently swapping bounds or dropping stated values. A future
expected-failure corpus can model that case explicitly. Total-level shipping
outside subtotal and nullable subtotals remain the coordinated invoice.v2 work
in #35 and #54.

## Offline rehearsal

Run `make accuracy-rehearsal` (or `uv run make accuracy-rehearsal`) before a paid
accuracy run. It loads only REVIEWED fixtures and feeds each expected record into
the existing FixtureClient, then submits the real document to an in-process API.
Caller auth, request validation, extraction validation and the scorer all run.
It creates a temporary database and restores the fixture environment on exit.

The output is labeled **OFFLINE REHEARSAL** and uses provider `fixture`, zero cost
and local latency. A perfect result proves the plumbing only; it is not provider
accuracy, T17 evidence, or a replacement for independent human label review.
Run it as a standalone development command, not in a concurrent serving process.
Use `ARGS='--doc-type uk_job_posting'` after job labels are REVIEWED; it currently
fails loudly because that reviewed corpus is empty. DRAFT files stay excluded.

### Total-only invoice convention

For `invoice_0007` and `invoice_0008`, the source states only a total. Because
invoice.v1 cannot represent a null subtotal (#35), these labels set
`subtotal_minor=total_minor`. This is a scoring convention, not an inferred
subtotal, and deliberately differs from a back-calculated ex-VAT subtotal. Do
not infer line items.
