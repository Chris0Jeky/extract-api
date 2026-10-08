# extract-api runbook: deploy, verify, roll back, rotate

How to put extract-api on Render (primary, ADR 0005) and run it there. Nothing in this repository
provisions anything: every step below that creates an account, a service, a secret or a domain is
the owner's, and none of it costs money until the Render service exists. Railway, the maintained
alternate, is at the end.

The moving parts:

| Piece | Where | What it does |
| --- | --- | --- |
| Image | `ghcr.io/chris0jeky/extract-api` | Built once per main commit by `.github/workflows/image.yml`: smoked, scanned, SBOM'd, attested, tagged `sha-<commit>`; `main` moves only to a proven digest |
| Service | Render, from `render.yaml` | One Starter instance, 1 GB disk at `/data`, health check `/readyz`, fixture mode until go-live |
| Deploy | `.github/workflows/deploy.yml` | Verifies provenance, deploys one digest, waits for `/readyz` to report it, checks one store and one fixture extraction |
| Logs | Render's log stream | One JSON line per event; one `extract.access` line per request (`docs/ops/OBSERVABILITY.md`) |
| Sizing | `docs/ops/SIZING.md` | Starter with `EXTRACT_MAX_CONCURRENCY=4`, measured |

## 1. One-time setup (owner)

Do these in order. `tasks/BACKLOG.md` (M5) tracks them.

**1.1 Make the image public.** The first main build after the image pipeline merged created the
package as private (GitHub's default). Render pulls it anonymously, and public packages cost
nothing. On GitHub: your profile, Packages, `extract-api`, Package settings, Danger zone, Change
visibility, Public. Check from a machine logged out of GHCR:

```bash
docker logout ghcr.io && docker pull ghcr.io/chris0jeky/extract-api:main
```

**1.2 Protect the `production` environment before it holds any secret.** The deploy workflow names
it, and GitHub creates an unprotected one on first use, so create it yourself first. Repository
Settings, Environments, New environment `production`: add yourself as a required reviewer, and
under deployment branches choose "Selected branches" with only `main`.

**1.3 Create the Render service.** Render dashboard, New, Blueprint, connect
`Chris0Jeky/extract-api`. Render reads `render.yaml` and prompts for each `sync: false` value: the
provider keys, models and prices. Leave them all blank for now; fixture mode reads none of them.
This creates the Starter service ($7 a month) and its 1 GB disk ($0.25 a month) in Frankfurt, and
deploys the current `main` image.

**1.4 Wire the deploy workflow.** In the Render service's Settings, copy the Deploy Hook URL and the
service's `onrender.com` URL. In the GitHub `production` environment add:

- secret `RENDER_DEPLOY_HOOK_URL`: the deploy hook URL (it is a credential: anyone holding it can
  redeploy the service);
- variable `EXTRACT_API_BASE_URL`: `https://<service>.onrender.com`;
- variable `EXTRACT_API_SMOKE_MODE`: `fixture`.

## 2. Deploy

Deploy a commit whose image pipeline succeeded on main:

```bash
gh run list -R Chris0Jeky/extract-api --workflow image.yml --branch main --status success --limit 1 --json headSha --jq ".[0].headSha"
```

```bash
gh workflow run deploy.yml -R Chris0Jeky/extract-api -f revision=<that sha> -f target=render
```

Approve the run when GitHub asks (the environment's required reviewer). The workflow refuses an image
that `image.yml` did not build and attest on main for that exact commit, deploys it by digest,
then fails unless all of these hold within ten minutes: `/readyz` answers 200 with that revision;
ten samples of `/readyz` all name the same `idempotency_store_id`; and, in fixture mode, one
extraction returns exactly the labelled `invoice_0001` record. Its job summary records the
previously deployed revision, which is the rollback target.

A Render deploy stops the old instance before starting the new one (a disk rules out overlap), so
expect a short gap. Clients retrying with the same `Idempotency-Key` are safe.

## 3. Verify by hand

```bash
curl -s https://<service>.onrender.com/readyz
```

Ready looks like `{"status":"ready","revision":"<sha>","idempotency_store_id":"<id>","provider_mode":"fixture"}`.
A 500 `internal_error` means the store cannot write. The log line `readiness probe failed` names the
cause: no disk at `/data` ("not on a persistent mount"), or a disk the app cannot write. The
`idempotency_store_id` should stay the same across deploys; a new one means the disk was replaced
and the 24-hour replay window restarted.

## 4. Go live (blocked on caller authentication)

The API has no caller authentication yet. Until the owner decision `extract-api-caller-auth`
(agent-hq inbox) is answered and its result is merged and deployed, keep the service in fixture
mode: a live provider behind a public URL would let anyone spend on your provider account. When it is:

1. In Render's environment for the service: delete `LLM_PROVIDER_MODE` and `FIXTURE_CANNED_TEXT`;
   set `OPENAI_API_KEY` (and/or `ANTHROPIC_API_KEY`), the model ids and the four per-million-token
   prices for the models you chose, from the provider's own pricing page; set the caller-key
   secret that the auth change names. Keep `EXTRACT_BUDGET_USD` set: it caps spend per process
   lifetime (it resets on every restart), and unset disables it.
2. Set the GitHub variable `EXTRACT_API_SMOKE_MODE` to `live`. CI never calls a paid provider, so
   the deploy then checks readiness and the store only.
3. Render restarts the service on an environment change. Check `/readyz` reports
   `"provider_mode":"live"`, then make one real extraction yourself and read its `extract.access`
   log line for `result`, `cost_usd` and `duration_ms`.

## 5. Roll back

Dispatch the deploy workflow again with the previous revision, the "Rollback target" in the failed or
regretted run's job summary:

```bash
gh workflow run deploy.yml -R Chris0Jeky/extract-api -f revision=<previous sha> -f target=render
```

It is the same path as a deploy, so the same proofs run. Rolling back never touches the disk: the
idempotency tables are created with `CREATE TABLE IF NOT EXISTS`, and an older revision ignores
tables it does not know. In an emergency with GitHub unavailable, Render's dashboard can roll back
to a previous deploy; that reuses the deploy's image, which is safe because the workflow always
deploys by digest.

## 6. Rotate secrets

Each rotation is: create the new value, switch to it, check, revoke the old one. No secret is ever
written to a file, a commit, a command line or a chat.

| Secret | Create | Switch | Check | Revoke |
| --- | --- | --- | --- | --- |
| Provider API key | The provider's console | Render environment (restarts the service) | `/readyz`, then the next real request's access line shows `result: ok` | The provider's console |
| `RENDER_DEPLOY_HOOK_URL` | Render service Settings, regenerate the deploy hook | GitHub `production` environment secret | The next deploy run reaches "Verify the deployed revision" | Confirm in Render that only the new hook exists |
| `RAILWAY_PROJECT_TOKEN` | Railway project Settings, Tokens | GitHub `production` environment secret | The next Railway deploy run | Delete the old token in Railway |
| Caller API keys (after the auth decision) | Per the auth change's docs | Per the auth change's docs | | |

A provider key rotation restarts the instance (a short gap, as in a deploy). Rotate the deploy hook
whenever anyone who should not have it may have seen it: it can redeploy, though only images that
exist in GHCR.

## 7. Domain

`api.deliverasoft.com` is reserved for this service in agent-hq's DNS plan
(`registry/hosting/dns-plan.json`: a CNAME to the Render hostname, not proxied, so Render's own
certificate and health checks see real traffic). It waits on the owner buying deliverasoft.com.
After that: add the custom domain in the Render service's Settings, create the CNAME at the DNS
provider, wait for Render to issue the certificate, then change `EXTRACT_API_BASE_URL` to
`https://api.deliverasoft.com`.

## 8. Railway (alternate)

Railway runs the same image. Its config-as-code (`railway.json`) only applies to a service built
from the repository, so for the promoted image set the same values in the dashboard:

1. New project, Deploy from Docker image, `ghcr.io/chris0jeky/extract-api:main` (public, step 1.1).
2. Add a volume mounted at `/data`. Leave `RAILWAY_RUN_UID` unset: the image starts as root, repairs
   the volume's ownership and drops to uid 10001 itself.
3. Settings: one replica (Railway refuses replicas with a volume anyway), health check path
   `/readyz`, restart on failure, no sleeping.
4. Variables: the same names and values as `render.yaml`'s `envVars`, including fixture mode,
   `EXTRACT_MAX_CONCURRENCY=4` for a 512 MB limit (16 at 1 GB) and `EXTRACT_BUDGET_USD`.
5. GitHub `production` environment: secret `RAILWAY_PROJECT_TOKEN` (a project token: the narrowest
   Railway credential), variables `RAILWAY_SERVICE_ID` and `RAILWAY_ENVIRONMENT_ID`, plus the same
   `EXTRACT_API_BASE_URL` and `EXTRACT_API_SMOKE_MODE`. Then deploy with `-f target=railway`.

The workflow's Railway step updates the service's image through Railway's public API; Railway
documents that field only for service creation, so the first Railway deploy is also the proof of
that step. If it fails, the error is loud and nothing changed.

## 9. Watching it

The five signals (`docs/ops/OBSERVABILITY.md`): readiness from `/readyz` (Render's health check, and
an external probe once the domain exists); request rate, errors and latency from `extract.access`
lines; CPU and memory from Render's metrics against `docs/ops/SIZING.md`; disk from Render's disk
metrics; backup does not apply, because `/data` holds only the disposable 24-hour replay cache.
Keep `LOG_LEVEL` at `INFO` in production (the access lines are INFO), and never set `OPENAI_LOG` or
`ANTHROPIC_LOG`: the SDKs then log request bodies.
