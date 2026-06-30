# STATUS - where extract-api is

Living snapshot for starting a new session strong. Last updated 2026-06-30.
Authoritative detail lives in `AGENTS.md` (rules), `tasks/BACKLOG.md` (tasks),
`docs/plan/PLAN.md` + `docs/adr/` (decisions). This file is the orientation.

## Merged to `main` (gate-green)

The full M2 + M3-engineering batch is merged (main HEAD `e404fac`; CI green). The
**invoice and job-posting paths are live end-to-end** for both providers, with idempotency,
PDF text, full taxonomy coverage, a per-run budget guard, and the deterministic accuracy
harness on `main`.

| Area | What is on main |
| --- | --- |
| M0 | config + pinned deps (ADR 0001), strict schemas + registry, FastAPI app, `llm/client.py` seam, CI + governance + `.claude` hooks/skills |
| T01-T06 | invoice schema completeness; OpenAI Responses path (strict json_schema, env-priced cost); validation-retry (1 retry / 2 attempts); `POST /v1/extract`; FixtureClient + offline smoke; taxonomy handlers; `harness/normalize.py`; default provider = openai |
| T08 | `JobPostingV1` completeness (explicit-null keys, salary cross-field validators) |
| T09-T10 | Anthropic structured-output path (native json_schema, mirror of T02); provider selection + `default` routing wired through the pipeline |
| T11-T12 | `api/idempotency.py` + SQLite store (WAL, first-writer-wins); endpoint wiring (replay on match, 409 on conflict, 24h TTL); smoke extended |
| T13-T14 | full error-taxonomy coverage (reserved codes + tripwire); PDF text via PyMuPDF (page/size caps, no OCR) |
| T16 / T18 | deterministic accuracy harness (`harness/run_accuracy.py` + `scoring.py`, NO LLM judge, `--live` mode); per-run USD budget guard -> `budget_exceeded` |
| #28 / #29 | framework 404/405 carry taxonomy codes; locked taxonomy reframed as a principle (one-code-per-non-200; `api/errors.py` is the source of truth; new codes need owner approval) |
| #21 / #25 / #38 | 5xx provider-detail sanitization; XDR fail-loud (no minor unit); gateway half-config fails loud (both providers) |

Locked architecture: the seam is text-based (`complete(json_schema) -> raw JSON text`,
re-validated by the retry loop); `llm/` never imports `api/`; `cost_usd` is env-priced
(no silent default that would mis-bill); retry = 1 retry / 2 attempts.

## Next up (gated on Chris / paid runs / Docker)

The code path to M3/M4 is merged; the published numbers still wait on:

- **T15** labeled fixtures (30-50 each) - blocks on Chris's labels + the **#36** T07 sign-off
  (flip the 10 invoice fixtures DRAFT -> REVIEWED).
- **T17** two-provider accuracy table - needs T15 + paid `--live` runs.
- **T20** README with measured numbers - follows T17.
- **T19** docker compose live - needs Docker (absent in the sandbox).
- **T21** gateway-readiness trace - needs a `--live` run.

Autonomous harness-hardening that needs neither labels nor paid runs is being worked off the
merged harness (tracked as issues, see below): **#52** (control-plane 402/409 skipped, not
scored all-missed), **#57** (`--live` robustness: malformed-2xx, configurable timeout,
misplaced-fixture fail-loud). **#46** (hallucination-rate denominator) is intentionally
deferred to T17 to avoid churning the exact-match accounting twice.

## Open tracked issues

- **#6**: commit `uv.lock` + frozen CI install (needs `uv`, absent in the sandbox).
- **#10**: periodic ISO-4217 refresh (needs external data).
- **#13**: hook-hardening backlog (sensitive: edits the agent safety hooks).
- **#32**: degrade-branch masks future non-404/405 HTTPExceptions (needs an owner taxonomy call).
- **#35**: consider nullable `subtotal_minor` for total-only invoices (owner call).
- **#42**: idempotency atomic reservation under concurrency (sequential contract is correct).
- **#46**: hallucination-rate denominator (T17 metric refinement, deferred to T17).
- **#52**: accuracy harness scores a control-plane 402 as all-fields-missed (autonomous fix in flight).
- **#54**: v1 invoice cannot represent total-level shipping/adjustment outside subtotal (v2 / owner).
- **#57**: `--live` accuracy-harness hardening; items 2-4 addressed in flight, item 1 (fold a
  failed-validation 422's billed spend into cost totals) stays open (needs the error body to carry `cost_usd`).

## Open questions for Chris

- **Push + merge authorization**: grant the explicit go to push the queued local branches and
  merge the queue. Per CLAUDE.md/AGENTS.md, agents never push or self-merge without it.
- **#36 sign-off**: merging it is the REVIEWED clearance for the 10 invoice fixtures (your labels).
- Older Q2/Q3/Q4 are resolved (Q3 = aggregate-only invoice math, confirmed).

## Operating notes

See `docs/agentic/GIT_WORKFLOW.md`: the safety hook blocks command strings that *describe*
destructive patterns (use `-F` files), run the full gate before every push, and the
stacked-merge flow under strict protection. The local, git-excluded `ORCHESTRATOR.md` is
the live working log.
