# extract-api PLAN

Positioning: I make LLM systems cheap, reliable, and provably valuable in
production. Until measured numbers exist, the README carries "Numbers pending:
measured, not promised."

## What it is

A synchronous, strict-schema LLM extraction service. Document in, one validated
structured record out, with per-field accuracy reported across two providers. It
fails loudly instead of silently coercing.

## Locked decisions

1. **Two doc types only:** `invoice`, `uk_job_posting`. Versioned schemas
   `invoice.v1`, `job_posting.v1`; the version travels in request and response.
2. **Pydantic v2 strict models.** No silent coercion anywhere.
3. **Validation-retry loop, max 1 retry (2 attempts total).** Attempt 1: provider
   structured output then strict Pydantic validate. On `ValidationError`, attempt 2
   appends the exact failure list (from `err.errors()`) plus the previous response
   to the prompt. Second failure returns 422 with the full failure trail. Log every
   retry with its error class.
4. **Error taxonomy: exactly one ErrorCode per non-200.** The enum in `api/errors.py` is
   the single source of truth; new members require owner approval and the locked invariant
   is one-code-per-non-200, not a frozen count. Current members: `validation_failed`,
   `low_confidence`, `unsupported_doc_type`, `provider_error`, `provider_timeout`,
   `budget_exceeded`, `idempotency_conflict`, `internal_error` (T05),
   `not_found` (issue #28), `method_not_allowed` (issue #28).
5. **Idempotency:** `Idempotency-Key` + `sha256(payload)` stored with the
   response. Same key + same hash replays (no model call, `replayed:true`); same
   key + different hash returns 409; TTL 24h. SQLite store (ADR 0004).
6. **Two providers behind one seam:** `llm/client.py` reads `LLM_BASE_URL` +
   `LLM_API_KEY` (+ `GATEWAY_BYPASS`). No other module imports a provider SDK.
7. **Synchronous API only.** Async job queue is a non-goal.
8. **Deterministic accuracy harness. No LLM judges anywhere.**
9. **OCR is a non-goal.** Text and pre-extracted PDF text only (PyMuPDF).
10. **Normalization:** dates to ISO 8601; money to integer minor units +
    ISO-4217 currency; a genuinely-absent field is `null`, never a guess.

## Structured outputs (ADR 0002)

Both providers offer guaranteed-conformance structured output (OpenAI
`responses.parse`/`chat.completions.parse`; Anthropic `messages.parse`). These
guarantee SHAPE, not SEMANTICS. Cross-field, normalization, and value constraints
are enforced by Pydantic AFTER parse, and that is what the retry loop catches.
Optional fields are null-unions so the strict schema stays valid. When
`LLM_BASE_URL` points at a backend without strict support, the client degrades to
JSON mode and the same Pydantic validate-and-retry holds.

## API contract

`POST /v1/extract`, header `Idempotency-Key`. Body: `doc_type`, `schema_version`,
`content` (text or base64 pdf), `provider` (`openai`|`anthropic`|`default`).
200 returns `{data, meta{provider, model, schema_version, attempts, replayed,
field_confidence, cost_usd, latency_ms}}`. 422 returns
`{error:"validation_failed", attempts, failures:[{field, constraint,
model_output}]}`. 409 returns `{error:"idempotency_conflict"}`. Every non-200
carries one taxonomy error.

`field_confidence` is heuristic (presence + validation pass + optional model
self-report), labeled as such. `cost_usd` is emitted per request from day one
(the gateway later surfaces cost per accepted extraction).

## M0 build reconciliation

The kickoff prompt lists schemas under both "strict Pydantic models" and
"scaffolding stubs". They are built as REAL strict models at M0 because the field
specs are fully given and `fixtures-validate` plus the 10 DRAFT fixtures require a
real schema to validate against. The NotImplementedError stubs are the behavior
modules (the extract pipeline, the SQLite store, the harness scoring, the real
provider calls). A FixtureClient behind the seam (accepted) gives a deterministic
offline path for `make smoke` and tests.

## Milestones

- **M1:** invoice path end-to-end with validation-retry; 10 fixtures passing.
- **M2:** job-posting path; idempotency live; full error taxonomy.
- **M3:** accuracy harness, both providers, table committed to `evals/reports/`;
  small budget guard.
- **M4:** deploy as a new docker-compose service on the Hetzner box; README with
  numbers.

## Non-goals

Async job queue; OCR; more than two doc types; LLM-judge scoring; calibrated
confidence; auth/multi-tenant (the gateway owns keys and budgets).

## Definition of done

Deployed endpoint; strict JSON schemas; documented validation failures;
per-field accuracy table across two providers; error taxonomy with observed
frequencies; idempotent retries; schema versioning. Claim nothing before all are
true.
