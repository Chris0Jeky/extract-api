# ADR-0007: Transport and infrastructure failure policy

- Status: Proposed
- Decision owner: repository owner
- Related: #74, #57, T17

## Context

Not every failed HTTP call says something about model quality. A DNS/connect/TLS failure may occur before any request reaches the service. A read timeout or connection reset may happen after the provider was billed. Provider 5xx and terminal model validation failures are different again. A credible benchmark must classify these states and avoid unsafe automatic retries.

## Decision

### Class A: provably unsent infrastructure failure

Examples: DNS resolution failure, TCP connection refusal, TLS negotiation failure before HTTP request transmission.

Policy:

- retry at most the approved small limit with bounded exponential backoff and jitter;
- record each attempt in the journal;
- treat terminal exhaustion as `infrastructure_failure`;
- exclude from semantic denominator;
- fail/abort the run when infrastructure failures exceed the approved threshold;
- cost is zero only when the client can prove no request was sent.

### Class B: ambiguous sent failure

Examples: read timeout, connection reset after request write, lost response.

Policy:

- do not automatically retry unless a run-specific idempotency contract proves no duplicate spend/result ambiguity;
- journal as `ambiguous_sent_failure` with cost `unknown` unless provider/gateway evidence gives a value;
- exclude from semantic denominator;
- prevent complete-run promotion until retried/reconciled under an explicit operator decision.

### Class C: service/provider response failure

Examples: HTTP 502/504, provider SDK error surfaced by the service.

Policy:

- record as provider/service reliability failure;
- include in accepted-extraction denominator as a failure when the model path was intended;
- do not invent field outcomes;
- include known billed cost;
- retry only according to the provider/client policy frozen in the manifest.

### Class D: terminal validation failure

HTTP 422 after the bounded semantic attempts.

Policy:

- classify as extraction/model-quality failure;
- include in accepted-extraction and strict end-to-end denominators;
- expose and include billed attempt cost;
- do not mark expected-null fields as missed;
- persist validation error summaries, not raw output.

### Class E: control-plane rejection

Examples: budget exhausted, idempotency conflict, authentication/rate limit at gateway.

Policy:

- classify separately from model quality;
- a planned budget boundary may be a skip; misconfiguration invalidates the run;
- report counts and reasons;
- no semantic score.

## Default thresholds

Threshold values belong in the run approval/manifest, not this ADR. Recommended initial behavior:

- one retry for Class A;
- zero automatic retries for Class B;
- abort a full run after two infrastructure failures or a small percentage, whichever is stricter;
- never publish a “complete” report with unresolved Class B outcomes.

## Consequences

- Model quality is not penalised for local network outages.
- Service reliability remains visible and can block promotion.
- Ambiguous spend is not silently duplicated.
- Operator decisions become explicit but rare.

## Acceptance tests

Cover connect refused, DNS/TLS setup error, read timeout, reset, malformed 2xx, 502, 504, 402, 409, terminal 422, unknown cost and infrastructure abort threshold.
