# ADR-0008: Corpus governance, review and versioning

- Status: Proposed
- Related: ADR 0003, T15, #79

## Context

The harness only scores `REVIEWED` labels, which is a strong foundation. The current corpus, however, is too small and unbalanced for the advertised two-domain benchmark. Agent-authored synthetic fixtures can accelerate creation, but agents must not certify their own ground truth. Label changes after seeing provider failures can also overfit the benchmark.

## Decision

### Fixture states

- `DRAFT`: may be authored/corrected by agents or humans; never scored in a published run.
- `REVIEWED`: content and expected output were checked by an accountable human; eligible for scoring.
- Future optional `HOLDOUT`: reviewed but excluded from routine prompt development and used for release candidates.

### Source classes

- `synthetic`: fully generated, no external rights dependency;
- `real_anonymized`: derived from a real document with privacy/provenance review.

Keep source mix visible by document type and report metrics by source class when sample size allows.

### Corpus target

For the first two-domain release, target 30-40 reviewed fixtures per document type, stratified across ordinary and edge cases. Quantity is not sufficient; every schema field and important null opportunity must have coverage.

### Sidecar manifest

Do not add evaluation-only tags to the runtime fixture contract. Generate a sidecar manifest containing:

- fixture path/hash;
- source/status;
- coverage tags;
- ambiguity/risk;
- reviewer and review timestamp;
- provenance reference;
- admissibility decision.

The complete reviewed fixture set and hashes produce a corpus version/hash frozen in each run manifest.

### Admissibility

A fixture may enter the scored corpus only if the current schema can faithfully express its content under documented label rules. Examples requiring exclusion or explicit convention include:

- total-level invoice adjustments not represented by v1;
- total-only invoices whose unstated subtotal is forced by v1;
- job compensation whose OTE/pro-rata basis cannot be expressed without misleading values;
- relative posted dates without a trusted reference date;
- ambiguous conditional sponsorship collapsed beyond policy.

### Review process

1. Agent/human authors DRAFT.
2. Validator and coverage linter pass.
3. Human reviews content against expected field by field.
4. High-ambiguity fixtures receive second review or remain DRAFT.
5. Promotion to REVIEWED is a human-authored/approved commit.
6. Changes after a benchmark create a new corpus version and rationale.

Do not silently edit labels under an existing run/corpus identity.

### Anti-overfitting

- Keep a private or protected holdout once corpus size permits.
- Record whether a fixture was inspected during prompt tuning.
- Review provider disagreements without automatically choosing the majority model.
- Prefer adding a new edge-case fixture over rewriting a valid old label to fit output.

## Consequences

- Agent drafting removes blank-page work while human accountability remains.
- Published numbers become attributable to a corpus version.
- Schema-inexpressible examples cannot quietly distort model quality.
- Real-fixture sourcing remains the main human bottleneck.

## Acceptance tests/checks

- DRAFT never enters live scoring;
- duplicate IDs/hashes are flagged;
- every REVIEWED fixture has reviewer/provenance metadata;
- manifest/corpus hash changes when any reviewed content/label changes;
- inadmissible tags block release selection;
- report includes counts by document type/source/status.
