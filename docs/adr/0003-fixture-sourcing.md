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
