# Extraction hosting reference

`manifest.json` declares where and how extract-api runs, in agent-hq's hosting-manifest v2
(`agent-hq/hosting-manifest@2`, defined by agent-hq `docs/hosting/HOSTING_MANIFEST_V2.md`). It is
metadata: it provisions nothing, and `activation_authorized` stays `false` until the owner
authorizes spend.

- The decision and the portability boundary: `docs/adr/0005-hosting-platform.md`.
- The single-store guarantee and the shared-authority design: `docs/adr/0004-idempotency-store.md`.
- Deploy, verify, roll back, rotate: `docs/ops/RUNBOOK.md`.
- Measured sizing: `docs/ops/SIZING.md`. Logs and the five signals: `docs/ops/OBSERVABILITY.md`.
- Owner provisioning steps: `tasks/BACKLOG.md`, M5.

Validate after any edit, from an agent-hq checkout:

```sh
py -3 scripts/hosting.py validate <path to this repo>/.hosting/manifest.json
```

The invariants hold whatever the platform: no unauthenticated public paid-model endpoint (fixture
mode until caller authentication exists), strict validation and idempotency semantics unchanged,
document content and credentials never in logs, exactly one idempotency store, and no spend,
public branding or domain change without the owner.
