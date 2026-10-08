# ADR 0005: Hosting platform and portability boundary

- Status: ACCEPTED (2026-10-08). Nothing is provisioned; provisioning is the owner's step.
- Deciders: the extract-api hosting-wave session, under the owner's 2026-10-08 delegation of
  hosting choices to the wave (spend and account creation stay owner-only).

## Context

The estate hosting research (2026-10-08) names extract-api "an excellent conventional PaaS
candidate": one small always-on container, Render Starter or Railway Hobby, one replica, a 1 GB
disk at `/data` for the idempotency SQLite (ADR 0004), and no queue, Redis or Postgres. The
service is synchronous, its heavy time is spent waiting on providers, and its only state is a
24-hour replay cache.

Facts checked against the providers' own pages on 2026-10-08:

- Render: "You can't scale a service to multiple instances if it has a disk attached", and
  "Adding a disk to a service prevents zero-downtime deploys" (render.com/docs/disks). A deploy
  hook deploys a specific tag or digest through its `imgURL` parameter
  (render.com/docs/deploy-hooks). Starter is 512 MB / 0.5 CPU at $7 a month; disks are $0.25 per
  GB-month (render.com/pricing). The Blueprint schema's plan enum goes from `0.5c-512mb`
  straight to `1c-2g`: Render has no 1 GB size.
- Railway: "Replicas cannot be used with volumes", and non-root images "will have permissions
  issues" on volumes unless `RAILWAY_RUN_UID=0` (docs.railway.com/reference/volumes). Hobby is
  $5 a month including $5 of usage. Config-as-code does not declare volumes.

## Decision

**Render is the primary platform; Railway is a maintained adapter; the existing
`docker-compose.yml` is the VPS adapter.** Render wins on predictability: a fixed price, a
declarative Blueprint that covers the disk, env and health check, and digest deploys through a
hook, which is exactly "build once, promote the artefact". Railway stays wired because its
metered pricing suits a mostly idle API, and because a second working target keeps switching
cheap. Region `frankfurt`, the closest Render region to the owner's UK domains.

`render.yaml` declares one `starter` web service with `runtime: image` (Render never builds
it), a 1 GB disk at `/data`, `numInstances: 1`, and `healthCheckPath: /readyz`. `railway.json`
declares one replica and the same health check. Secrets are named with `sync: false` and never
valued. `tests/test_deploy_descriptors.py` pins these invariants.

**Safe by default.** A freshly created service runs `LLM_PROVIDER_MODE=fixture` (answers come
from the deterministic FixtureClient, so no provider spend is possible) with the process spend
cap `EXTRACT_BUDGET_USD` set rather than unset (unset disables `api/budget.py`'s guard). Going
live is a runbook step, gated on caller authentication: the API has none today, and the
hosting manifest's invariant forbids an unauthenticated public paid-model endpoint.

**Readiness gates deploys.** `/readyz` commits a one-row write to the idempotency store and
reports the image revision and provider mode; it renders `internal_error` (500) when the store
cannot write. Because a disk prevents zero-downtime deploys on Render, a new instance replaces
the old one; pointing the platform health check at `/readyz` instead of `/healthz` means a
deploy with a missing, read-only or root-owned disk fails its health check instead of serving
requests that silently skip idempotency storage. The probe runs on its own one-token thread
limiter so a saturated extraction pool cannot starve the health check into a restart.

## The portability boundary

Everything platform-neutral is the contract; everything else is an adapter of a few lines.

| Contract (same on every platform) | Adapter (per platform) |
| --- | --- |
| One OCI image, built once in CI, deployed by digest | `render.yaml`; `railway.json` plus dashboard settings; `docker-compose.yml` |
| Env vars documented in `.env.example`; secrets named only | Where secrets are entered (Render prompt, Railway variables, VPS `.env`) |
| Port 8200, `/healthz` liveness, `/readyz` readiness | The platform's health-check field |
| Persistent volume at `/data`, exactly one writer | Disk, volume or named volume |
| Deploy = promote a digest; rollback = promote the previous digest | Render deploy hook; Railway API; `docker compose pull && up -d` |

Switching platform is: create the service from its adapter, enter the named secrets, deploy
the current digest, and point DNS. The idempotency cache does not need migrating: losing it
only drops the 24-hour replay window (ADR 0004).

## Railway specifics

- Railway reads `railway.json` only for a repository-linked service, where Railway builds the
  Dockerfile itself; that is a fallback, not the promoted artefact. The promoted path is an
  image-sourced service, whose volume, env and health check the runbook sets in the dashboard
  to match `railway.json`.
- Railway volumes need `RAILWAY_RUN_UID=0`. The image entrypoint (added with the image pipeline) therefore drops back to the
  unprivileged `extract` user after fixing `/data` ownership when started as root, so the app
  never runs as root on any platform.
- The deploy workflow's Railway step updates the service's image source through Railway's
  public GraphQL API. Railway documents `source.image` only on service creation, so that step
  is unverified until the owner's first Railway deploy.

## Consequences

- Horizontal scale is off on both platforms, and both platforms enforce it while a disk or
  volume is attached. Scaling out first needs a shared idempotency authority (ADR 0004).
- Every Render deploy has a short gap while the old instance stops before the new one starts.
  Accepted for a single-owner API; a client retrying with the same `Idempotency-Key` is safe.
- Sizing (512 MB Starter or the 2 GB `1c-2g` size) is decided by the fixture-mode load test,
  not guessed; until it is recorded, `plan: starter` stands.
- Cost at the recommended size: about $7.25 a month on Render, or the $5 Railway floor.
  Nothing is bought until the owner decides to provision.
