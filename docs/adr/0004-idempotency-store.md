# ADR 0004: Idempotency store

- Status: ACCEPTED (2026-06-13).
- Deciders: Chris.

## Context

Idempotency is locked: `Idempotency-Key` header + `sha256(payload)` stored with
the response. Same key + same hash replays (no model call, `replayed:true`); same
key + different hash returns 409; TTL 24h. The open question was the backend.

## Decision

**SQLite for v1.** A single file-backed store (`idempotency.sqlite`, gitignored)
with one table `(key PRIMARY KEY, payload_sha256, response_json, status_code,
created_at)`. A TTL sweep (or lazy check on read) expires rows older than 24h.

Rationale: trivially deployable (no extra service in the compose stack), survives
restarts, zero network dependency, and the access pattern is a primary-key
lookup. The store is a thin interface (`get`, `put`, `sweep`), so the gateway-era
swap to the gateway's Postgres instance is one adapter, not a rewrite.

## Consequences

- `*.sqlite` is gitignored; the store file never enters version control.
- SQLite with WAL mode handles the expected synchronous, low-concurrency load.
- The 409-on-mismatch and replay-on-match semantics live in
  `api/idempotency.py` behind the store interface, independent of backend.
