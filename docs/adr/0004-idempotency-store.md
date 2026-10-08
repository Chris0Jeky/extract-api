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

## Amendment (2026-10-08): single-replica safety and the shared authority

Hosting on a PaaS (ADR 0005) adds a failure the original decision only implied: two replicas
with two disks are two independent stores. A retry with the same `Idempotency-Key` that lands
on the other replica is not replayed, so the model runs and bills twice, and a reused key with
a different payload is not caught as a conflict. Nothing fails; the guarantee just stops
holding. The store is therefore a single-writer authority, and that is enforced, not assumed.

### How one store is enforced today

1. **The platform.** Render: "You can't scale a service to multiple instances if it has a disk
   attached." Railway: "Replicas cannot be used with volumes." While the store has a disk, a
   second replica cannot be created on either platform.
2. **The app requires a mount.** With `IDEMPOTENCY_REQUIRE_PERSISTENT_MOUNT=1` (set in the
   image, `docker-compose.yml` and `render.yaml`), `/readyz` fails unless the store's directory
   is on a different device from `/`. On Render and Railway, whose health checks use `/readyz`,
   a service whose disk was removed (for example to unlock scaling) fails its health check
   instead of serving from a disposable container layer, so rule 1 holds there: no disk, no
   ready replica; a disk, one replica. The check proves "a mount", not "a persistent mount": a
   tmpfs at `/data` would pass. It gates only what probes `/readyz`; compose's healthcheck
   probes `/healthz`, so on a VPS the compose file's volume line is the guard.
3. **The descriptors are pinned.** `tests/test_deploy_descriptors.py` fails CI if
   `numInstances`, `numReplicas`, autoscaling or the `/data` disk changes.
4. **The store is visible.** Each store mints a `store_id` once and keeps it in the file. It
   appears in `/readyz` and in the `X-Idempotency-Store` header of every successful or
   replayed keyed response (error bodies are rendered by the taxonomy handlers and omit it). A
   deploy check that samples `/readyz` repeatedly sees more than one id if two stores ever
   serve, and a client can see that a retry reached a different store. A replaced or wiped
   disk also shows up as a new id.

Several processes sharing one file on one host (uvicorn `--workers`, or compose replicas on
one named volume) are still one store: SQLite's file locking serialises them correctly.

### When to build a shared authority

Build it when any of these is true, not before:

- One instance cannot carry the measured load at the largest single size the platform offers
  (the load-test numbers in `docs/ops/` are the evidence).
- Deploys must stop dropping requests: a disk rules out zero-downtime deploys on Render, and
  overlapping old and new instances is a second writer.
- The service runs in more than one region.
- The gateway era (PLAN week 10) brings a managed Postgres that already exists for other
  reasons.

### Design (decided now, built later)

- **Backend: Postgres.** One table with the same columns plus `state` (`pending` or `done`)
  and `lease_expires_at`, keyed on `key`. It gives atomic insert-if-absent and durable rows
  with plain SQL. Rejected: Redis (a second system whose durability depends on persistence
  settings, for a few rows a day), Cloudflare KV (eventually consistent, so two replicas can
  both miss), and D1 (strongly consistent, but only reachable through a Worker, adding a hop
  and a platform to an API that has neither).
- **Atomic reservation, which also closes #42.** Before the model call:
  `INSERT ... ON CONFLICT (key) DO NOTHING RETURNING key` writes a `pending` row with a lease
  of the provider timeout plus margin. The winner calls the model and updates the row to
  `done` with the response; on failure it deletes the row so the key stays retryable, as
  today. A loser reads the row: `done` with the same hash replays; a different hash is still
  `idempotency_conflict` (409); `pending` with the same hash waits for the lease, polling, then
  replays or takes over an expired lease. Every transition is a conditional write: the
  reservation carries an owner token, a takeover is
  `UPDATE ... SET owner = :new, lease_expires_at = :later WHERE key = :k AND state = 'pending'
  AND lease_expires_at < now()` (one winner among several losers), and completion is
  `UPDATE ... WHERE key = :k AND owner = :token`, so a stalled winner that outlived its lease
  cannot overwrite the new owner. The 24-hour TTL needs the same care: an expired `done` row
  must not block or be replayed, so the reservation is
  `ON CONFLICT (key) DO UPDATE ... WHERE idempotency.created_at < :ttl_cutoff`, matching
  today's "an expired hit is no hit". Replay, 409, the TTL and "only a 200 is stored" keep
  their current meaning. A thread stall longer than the lease can still run the model twice;
  the lease bounds that window, it cannot close it.
- **Seam.** The `IdempotencyStore` protocol gains `reserve` and `release` and keeps `get`,
  `put`, `sweep`, `probe` and `store_id`. SQLite implements `reserve` as the same insert, so
  both backends share one code path. `IDEMPOTENCY_BACKEND=postgres` selects it, and the
  persistent-mount requirement no longer applies there.
- **Cutover.** The cache is disposable by contract, so the switch deploys the Postgres
  backend and accepts losing at most 24 hours of replay rows. No data migration. Only after
  that are replicas raised above one and the disk detached.
