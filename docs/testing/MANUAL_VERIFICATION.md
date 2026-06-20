# Manual verification (headless API)

extract-api has no UI, so manual testing is a documented, repeatable API check,
not click-through. Record the metadata below before and after a run, in the PR's
Test plan or the linked issue.

## Run metadata template (required)

```
- date/time (UTC):
- commit SHA:
- OS / Python:
- env: LLM_PROVIDER_MODE / provider / model / GATEWAY_BYPASS
- artifacts: (logs, response bodies saved)
```

## Checks

Boot the service (`make dev`, then `http://127.0.0.1:8200/docs`) or drive it with
the offline smoke (`make smoke`).

1. **Liveness:** `GET /healthz` returns 200 `{"status":"ok"}`.
2. **Taxonomy spot-checks** (one row per error once the pipeline lands in M1/M2):
   - 200 with full `meta` on a known-good fixture.
   - 422 `validation_failed` with the full failure trail on a second-failure case.
   - 409 `idempotency_conflict` on same key + different payload.
   - 422 `unsupported_doc_type` on an unknown `schema_version`.
   - `provider_timeout` / `provider_error` via an induced provider fault.
3. **Idempotency:** same key + same payload replays (`meta.replayed: true`, no
   model call); confirm via logs that no provider call was made.
4. **Live extraction (paid, M3+):** one real extraction per provider on a known
   fixture; record `cost_usd` and `latency_ms`.
5. **Gateway trace (M4):** capture a before/after trace of one golden extraction
   around the `LLM_BASE_URL` flip; this is the gateway-migration evidence.

A red result is a real problem: file it, do not wave it through.
