# extract-api

> I make LLM systems cheap, reliable, and provably valuable in production.

A strict-schema LLM extraction service that turns documents into validated
structured data and reports per-field accuracy across two providers (OpenAI and
Anthropic). It uses Pydantic v2 strict models with a validation-retry loop that
appends the exact failure list back to the model, and it fails loudly instead of
silently coercing. Both providers sit behind one thin `llm/client.py` seam, so
moving onto an LLM gateway later is an environment change, not a rewrite.

## Numbers pending: measured, not promised

The headline artifact is the accuracy table (per-field exact-match rate,
null-handling correctness, and hallucinated-field rate across two providers, with
cost and p50/p95 latency). It is produced by a deterministic harness with no LLM
judges. Until those numbers exist this README leads with this block, never a
capability claim.

## API contract

```
POST /v1/extract
Headers: Idempotency-Key: <client uuid>
Body: {
  "doc_type": "invoice" | "uk_job_posting",
  "schema_version": "v1",
  "content": "<document text, or a base64 PDF when content_format is pdf_base64>",
  "content_format": "text" | "pdf_base64",   // optional, default "text"
  "provider": "openai" | "anthropic" | "default"
}
// PDF callers MUST set "content_format": "pdf_base64"; otherwise the base64 is treated
// as literal text. PDF text is extracted with PyMuPDF (no OCR).

200 OK:
{ "data": { ...validated fields... },
  "meta": { "provider", "model", "schema_version", "attempts", "replayed",
            "field_confidence", "cost_usd", "latency_ms" } }

422 Unprocessable Entity (terminal provider-validation retry):
{ "error": "validation_failed",
  "detail": "extraction failed strict validation after 2 attempt(s)",
  "attempts": 2,
  "trail": [
    [ { "loc", "type", "msg" } ],
    [ { "loc", "type", "msg" } ]
  ] }

422 Unprocessable Entity (pre-request validation):
{ "error": "validation_failed", "detail": "request validation failed" }
// Malformed requests and empty or oversized content fail before any provider call.
// The terminal provider-validation response does not include cost_usd yet (#57).

409 Conflict:
{ "error": "idempotency_conflict" }   // same key, different payload hash
```

Idempotency: `Idempotency-Key` + `sha256(payload)` is stored with the response.
For a successful response, same key + same hash replays the stored response with
`meta.replayed: true`, preserves the original `meta.cost_usd`, and makes no provider
call or new provider spend. Same key + different hash is a 409; TTL 24h.

`field_confidence` is a presence-only **heuristic** (1.0 for a present value, 0.0 for an
explicit null), not a calibrated probability. The README will say so wherever the
numbers appear.

## Error taxonomy

Every non-200 carries exactly one error code, including framework routing errors.
Observed frequencies are filled in from the accuracy run (numbers pending). One code is
**reserved** (`low_confidence`): it has a fixed status and renders correctly, but no live
request path emits it yet because confidence-gating is unbuilt.

| error | HTTP | meaning | frequency |
| --- | --- | --- | --- |
| `validation_failed` | 422 | output failed strict validation twice, or a malformed request | TBD |
| `low_confidence` | 422 | confidence below threshold (reserved: confidence-gating not built) | n/a (reserved) |
| `unsupported_doc_type` | 422 | no schema for (doc_type, schema_version), or an out-of-Literal doc_type | TBD |
| `provider_error` | 502 | provider call failed | TBD |
| `provider_timeout` | 504 | provider call timed out | TBD |
| `budget_exceeded` | 402 | per-run USD cap (EXTRACT_BUDGET_USD) reached | TBD |
| `idempotency_conflict` | 409 | same key, different payload | TBD |
| `internal_error` | 500 | unexpected or unmapped server error | TBD |
| `not_found` | 404 | no such route | TBD |
| `method_not_allowed` | 405 | wrong HTTP method for the route | TBD |

## Non-goals

Async job queue; OCR (text and pre-extracted PDF text only); more than two doc
types in v1; LLM-judge scoring; calibrated confidence; auth and multi-tenant (the
gateway owns keys and budgets).

## Status

Engineering-complete through M3 and deployable. The invoice and job-posting paths are live
end-to-end for both providers (OpenAI + Anthropic) behind the `llm/client.py` seam, with the
validation-retry loop, idempotency (SQLite), PDF text extraction (PyMuPDF, no OCR), full error
taxonomy, a per-run USD budget guard, and the deterministic accuracy harness. The container
builds and `docker compose up` serves `/v1/extract` with a green healthcheck (verified offline).

What is still **pending**: the published accuracy table needs human-reviewed fixtures and paid
`--live` runs against both providers, so the "Numbers pending" block above stays until then.
Build sequence and tasks live in `tasks/BACKLOG.md`; the plan and decisions live in `docs/`; the
living status snapshot is `docs/STATUS.md`.

## Development

```
make help        # list targets
make dev         # run the API locally (uvicorn)
make test        # pytest with coverage
make typecheck   # mypy strict
make smoke       # deterministic offline smoke (no paid model calls)
```

## Deploy (Docker)

```
cp .env.example .env      # fill in provider keys + per-model prices (never commit .env)
docker compose up -d      # builds the image, serves on :8200, healthcheck hits /healthz
```

The image is `python:3.13-slim` with the pinned project metadata (no OCR system libraries by
design). Provider routing is env-only, so the future gateway migration is a change to `.env`
(`LLM_BASE_URL` + `LLM_API_KEY`), not to the image or compose file. For a paid-call-free check,
set `LLM_PROVIDER_MODE=fixture` + `FIXTURE_CANNED_TEXT=<canned model output>` in `.env` and the
container serves `/v1/extract` deterministically offline. `FIXTURE_CANNED_TEXT` must be a JSON
string that validates against the requested `doc_type`/`schema_version` (e.g. a valid `invoice.v1`
object); arbitrary text will fail the validation-retry loop and return a 422, by design.

The image runs as an unprivileged user and defaults `IDEMPOTENCY_DB_PATH` to
`/data/idempotency.sqlite`. Compose mounts its named `idempotency-data` volume at `/data` and
forces the same path over the relative local default in `.env`, so replay records survive container
replacement or recreation while that volume is retained. `docker compose down --volumes`
intentionally destroys those replay records.
