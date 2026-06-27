# STATUS - where extract-api is

Living snapshot for starting a new session strong. Last updated 2026-06-27.
Authoritative detail lives in `AGENTS.md` (rules), `tasks/BACKLOG.md` (tasks),
`docs/plan/PLAN.md` + `docs/adr/` (decisions). This file is the orientation.

## Merged to `main` (gate-green)

M0 + all of M1's engineering (T01-T06) + T08 + the full error-taxonomy work are merged
(through PR #34). The **invoice path is live end-to-end**: `POST /v1/extract` ->
resolve schema -> resolve content -> OpenAI client -> validation-retry pipeline ->
`data` + full `meta`, with the taxonomy wired for every non-200, offline `make smoke`,
and the normalization helpers.

| Area | What is on main |
| --- | --- |
| M0 | config + pinned deps (ADR 0001), strict schemas + registry, FastAPI app, `llm/client.py` seam, CI + governance + `.claude` hooks/skills |
| T01-T03 | invoice schema completeness; OpenAI Responses path (strict json_schema, env-priced cost); validation-retry loop (1 retry / 2 attempts) |
| T04-T06 + Q8 | `POST /v1/extract` happy path; FixtureClient + offline smoke; full taxonomy wiring (`internal_error`, RequestValidationError, catch-all); `harness/normalize.py`; default provider = openai |
| T08 | `JobPostingV1` completeness (explicit-null keys, salary cross-field validators) |
| #28 / #29 | framework 404/405 carry taxonomy codes; locked taxonomy reframed as a principle (one-code-per-non-200; `api/errors.py` is the source of truth; new codes need owner approval) |

Locked architecture: the seam is text-based (`complete(json_schema) -> raw JSON text`,
re-validated by the retry loop); `llm/` never imports `api/`; `cost_usd` is env-priced
(no silent default that would mis-bill); retry = 1 retry / 2 attempts.

## Queued for merge (reviewed + CI-green, NOT merged)

A ~15-PR M2/M3 batch is queued. Each PR is gate-green with two independent adversarial
reviews + gemini clean; **none is self-merged** (the never-self-merge red line holds -
merge authorization is granted explicitly per run). Merge **oldest-first**:

```
main <- #37 T09 anthropic <- #39 T10 routing <- #40 T11 idem store <- #41 T12 idem wiring
     <- #43 T13 taxonomy <- #44 T14 pdf <- #48 (#21 5xx sanitize) <- #49 (#22 fc docs)
     <- #50 T18 budget <- #51 failed-call cost <- #53 (#38 gateway fail-loud)
```

Off-main, independent (merge any time): **#45** (T16 accuracy harness), **#47** (#25 XDR
fail-loud), **#55** (dependabot-auto-merge fix). Held for Chris's editorial sign-off:
**#36** (T07: flip the 10 invoice fixtures DRAFT -> REVIEWED, a ground-truth label change).

## Next up (after the merge)

Merging the queue unblocks: **T17** (two-provider accuracy table - needs paid `--live`
runs), **T19** (docker compose live), **T20** (README with measured numbers), **T21**
(gateway-readiness trace). **T15** (30-50 new labeled fixtures) blocks on Chris's labels.

## Open tracked issues

- **#6**: commit `uv.lock` + frozen CI install (needs `uv`, absent in the sandbox).
- **#9**: provider JSON-schema sanitization - verified resolved by code; close on stack merge.
- **#10**: periodic ISO-4217 refresh (needs external data).
- **#13**: hook-hardening backlog (sensitive: edits the agent safety hooks).
- **#32**: degrade-branch masks future non-404/405 HTTPExceptions (needs an owner taxonomy call).
- **#35**: consider nullable `subtotal_minor` for total-only invoices.
- **#42**: idempotency atomic reservation under concurrency (sequential contract is correct).
- **#46**: hallucination-rate denominator (T17 metric refinement).
- **#52**: accuracy harness scores a control-plane 402 as an all-fields-missed extraction (T17).
- **#54**: v1 invoice cannot represent total-level shipping/adjustment outside subtotal (v2 / owner).

## Open questions for Chris

- **Merge authorization**: grant merge auth (or merge the queue oldest-first). Never self-merged.
- **#36 sign-off**: merging it is the REVIEWED clearance for the 10 invoice fixtures (your labels).
- Older Q2/Q3/Q4 are resolved (Q3 = aggregate-only invoice math, confirmed).

## Operating notes

See `docs/agentic/GIT_WORKFLOW.md`: the safety hook blocks command strings that *describe*
destructive patterns (use `-F` files), run the full gate before every push, and the
stacked-merge flow under strict protection. The local, git-excluded `ORCHESTRATOR.md` is
the live working log.
