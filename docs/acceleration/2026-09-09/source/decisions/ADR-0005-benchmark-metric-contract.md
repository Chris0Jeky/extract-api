# ADR-0005: Layered benchmark metric contract

- Status: Proposed
- Decision owners: repository owner for metric meaning; agent for implementation
- Supersedes: the implicit single-layer accounting in the current harness
- Related: #46, #57, #74, T17

## Context

The current harness records top-level field outcomes and treats a failed extraction as every field being missed. It also divides hallucinated fields by all scored fields. These choices are conservative in one sense but semantically inconsistent:

- an expected-null field on a failed extraction is not a missed real value;
- a model may hallucinate every absent field while retaining a low all-fields rate;
- transport/service reliability and model semantic quality are blended;
- success-only cost/latency can improve when more requests fail;
- one nested line-item error turns the whole list into a single opaque mismatch.

Published evidence needs denominators that a reader can understand and reproduce.

## Decision

### 1. Three primary layers plus strict end-to-end success

#### Request layer

Every selected fixture receives one terminal request classification:

- `completed_response`;
- `infrastructure_failure`;
- `provider_failure`;
- `control_plane_skip`;
- `operator_abort`.

This layer reports attempted count, infrastructure reachability, skips and failure taxonomy.

#### Extraction layer

For requests that reached the extraction service/model path, report:

- accepted extraction rate (`HTTP 200 schema-valid response / eligible model-reaching fixtures`);
- first-pass schema-valid rate;
- retry recovery rate;
- terminal validation failure rate;
- provider error/timeout rate.

#### Semantic layer

Semantic field comparisons are defined only for accepted schema-valid predictions. For each field/path opportunity:

- `value_exact`: expected non-null and exactly equal;
- `value_incorrect`: expected non-null and predicted non-null but unequal;
- `value_missing`: expected non-null and predicted null;
- `null_correct`: expected null and predicted null;
- `hallucinated`: expected null and predicted non-null.

A request with no prediction is represented as `no_prediction`; it is not rewritten into false per-field observations.

#### Strict end-to-end layer

To ensure failed extraction is not hidden by success-only semantic tables, report:

`fully_correct_documents / all eligible fixtures`

A fully correct document must have a completed accepted extraction and every scored field/path exact under the declared contract.

### 2. Hallucination headline denominator

Headline hallucination rate is:

`hallucinated / expected_null_opportunities`

Report the historical all-fields fraction only as secondary context, clearly labelled.

Null correctness is:

`null_correct / expected_null_opportunities`

These are complementary when a prediction exists.

### 3. Value metrics

- value availability/recall: `(value_exact + value_incorrect) / expected_nonnull_opportunities`;
- exact value accuracy: `value_exact / expected_nonnull_opportunities`;
- conditional exactness when present: `value_exact / (value_exact + value_incorrect)`.

### 4. Nested invoice items

Keep whole-field exactness for `line_items`. Add deterministic index-aligned path metrics such as:

- `line_items[0].description`;
- `line_items[0].quantity`;
- `line_items[0].unit_price_minor`;
- `line_items[0].amount_minor`.

Do not add fuzzy or LLM-based alignment in v1. A reordered list is a whole-list mismatch and path mismatch under the order-sensitive contract.

### 5. Cost and latency

Report:

- total attempted spend;
- accepted-response spend;
- terminal validation/provider failure spend when known;
- unknown-cost event count;
- cost per attempted document;
- cost per accepted document;
- cost per fully correct document;
- terminal-request p50/p95 latency;
- accepted-only p50/p95 latency;
- retry count distribution and token totals.

Unknown cost is not zero. The manifest declares the cost source and whether unknown cost invalidates promotion.

### 6. Sample size and uncertainty

Every rate table displays numerator/denominator and `n`. Avoid presenting p95 as stable when terminal sample size is very small. Add Wilson intervals for binary rates or a documented bootstrap for paired comparisons once the implementation remains deterministic.

### 7. Promotion rule

A report is `complete` only when:

- all eligible fixtures have terminal journal states;
- manifest identity remains consistent;
- infrastructure failures do not exceed the approved threshold;
- no journal corruption/unknown fixture exists;
- the report is generated from the journal;
- a human approves public claims.

Incomplete reports may be inspected but cannot replace the README “Numbers pending” block or become a gate baseline.

## Consequences

### Positive

- Reliability and semantic quality become distinguishable.
- Hallucination is measured where it can occur.
- Failures still penalize strict end-to-end success without inventing false field observations.
- Cost per useful result becomes optimisable.
- The same contract supports release gating.

### Negative

- Existing snapshots and report columns change.
- More counters and explicit states are required.
- Readers must understand layered metrics rather than one headline percentage.

## Implementation notes

- Add explicit `RequestOutcome`, `ExtractionOutcome` and `FieldOutcome` enums/dataclasses.
- Make summary derivation pure over journal records.
- Keep field comparison deterministic and schema-derived.
- Add invariant tests proving denominators and complements.
- Use `implementation/reference_metrics.py` as a design sketch, not a drop-in patch.

## Acceptance tests

- expected-null + predicted-null increments `null_correct`, not generic value match;
- expected-null + predicted value increments hallucination opportunity;
- failed extraction creates `no_prediction` and decreases strict document success, but does not increment `value_missing` for expected-null fields;
- accepted extraction with one wrong line amount fails document exact match and identifies the path;
- failed 422 spend appears in attempted/failed cost;
- success-only semantic rates and all-fixture strict success are both present;
- report displays numerator/denominator for every rate.
