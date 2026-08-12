# ADR 0003: Fixture sourcing for job postings

- Status: ACCEPTED (2026-06-13).
- Deciders: Chris.

## Context

The accuracy harness needs 30 to 50 labeled fixtures per doc type. UK job
postings carry the interesting ambiguity (salary ranges, remote policy, visa
sponsorship, seniority) but real ones carry PII and copyrighted text. Labels are
the normalized expected output and must be trustworthy ground truth.

## Decision

**50/50 split, each file labeled which it is.**

- ~50% hand-collected real UK postings, fully anonymized: no real company names,
  people, emails, tax IDs, or addresses. Keep the genuine ambiguity.
- ~50% synthetic postings that deliberately exercise edge cases: inverted salary
  ranges, "competitive" salary (the canonical retry trigger), missing fields that
  must come back `null`, different salary periods, visa-wording variety.
- Every fixture carries `source: real_anonymized | synthetic` and `label_status:
  DRAFT | REVIEWED`. DRAFT labels are never counted until a human flips them to
  REVIEWED. Invoices follow the same discipline and may lean synthetic.

## Consequences

- The README can honestly state the real/synthetic split and the anonymization
  rule, which strengthens the accuracy table's credibility.
- Synthetic fixtures guarantee coverage of the failure modes that make the
  error-taxonomy frequencies meaningful.
- The DRAFT-versus-REVIEWED gate is enforced by `fixtures-validate` and by the
  harness, which scores only REVIEWED labels.
- A real or anonymized fixture also requires documented source provenance and a
  licence-compatibility review before commit. External source text does not
  inherit the repository's GPL licence merely by anonymization or inclusion.

## Labeling convention: invoice `line_items` (added 2026-07-03)

A `line_items` entry requires all of `description`, `quantity`, `unit_price_minor`, and
`amount_minor`. The document must state (or make unambiguous) a **quantity and a unit price**
for a line to be labeled: e.g. "Office chairs x4 at GBP 125.00" or an itemized table. A document
that gives only a described charge and a single amount, with no quantity/unit breakdown (e.g.
"Consulting services / Amount: USD 1,250.00"), is labeled `line_items: null`, because inferring
`quantity: 1` and `unit_price == amount` would be guessing values the document does not state
(the project rule: never guess an absent field). A bare total with no line description is likewise
`null`.

This is a deliberate strictness tradeoff and it is not free: against a `null` label, a model that
emits the reasonable single inferred line scores as a hallucinated field; against a single-line
label, a model that emits `null` scores as a miss. The convention favors literal document fidelity
(the harness measures exact match, not plausibility), and it must be applied CONSISTENTLY across
the corpus so identically-shaped documents get identical labels (the 10 invoice fixtures follow it:
0001/0004/0005/0009/0010 have explicit-qty/unit lines; 0002/0003/0006/0007/0008 are `null`).
