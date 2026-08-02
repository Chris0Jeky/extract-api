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

The Docker image defaults `IDEMPOTENCY_DB_PATH` to `/data/idempotency.sqlite` and
runs as an unprivileged user that owns `/data`, so the first keyed request can
initialize SQLite without writing the application directory. Docker Compose binds its
named `idempotency-data` volume at `/data` and explicitly retains that same path over
the relative local default. The volume preserves the v1 replay window across container
replacement or recreation, not across intentional volume deletion.

## Consequences

- `*.sqlite` is gitignored; the store file never enters version control.
- SQLite with WAL mode handles the expected synchronous, low-concurrency load.
- The 409-on-mismatch and replay-on-match semantics live in
  `api/idempotency.py` behind the store interface, independent of backend.
- `docker compose down --volumes`, an explicit volume delete, or a lost host discards
  replay rows. This remains a single-host v1 store, not a shared-volume scaling design.
