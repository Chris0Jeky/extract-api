# STATUS - where extract-api is

Living snapshot for starting a new session strong. Last updated 2026-07-03.
Authoritative detail lives in `AGENTS.md` (rules), `tasks/BACKLOG.md` (tasks),
`docs/plan/PLAN.md` + `docs/adr/` (decisions). This file is the orientation.

## Start here (next session)

Engineering is complete through M3 + Docker (T19). Nothing below is blocked on code you cannot
write; the remaining gates are Chris's fixture labels and paid provider calls. Priority order:

1. **#6 uv.lock + frozen CI** - now unblocked (`pip install uv` works; CI/Linux has `uv`). Clean,
   offline, no paid calls. The single best next autonomous slice.
2. **T15** - more labeled fixtures (Chris's labels), then
3. **T17** - two-provider accuracy table. This needs PAID `--live` runs AND two small code changes
   first: the #46 null-handling/hallucination-denominator metric and #57 item 1 (`cost_usd` in the
   422 body, contract pre-approved). Do the code, then the paid run, then
4. **T20** (README numbers, replaces the "Numbers pending" block) and **T21** (gateway trace).

Tidy-up left for the next loop: prune the merged remote branches (`feat/t09..t18`, `fix/*`); the
git-excluded `ORCHESTRATOR.md` at repo root is the detailed working log. Owner product calls
(#35/#54 -> invoice.v2; #42/#32 documented-scope; #13 sensitive) are recorded on each issue.

## Merged to `main` (gate-green)

Engineering-complete through M3, and deployable. main HEAD is `fab9042` plus the 2026-07-03
slices below; CI green. The **invoice and job-posting paths are live end-to-end** for both
providers, with idempotency, PDF text, full taxonomy coverage, a per-run budget guard, the
deterministic accuracy harness, and a verified Docker deployment.

| Area | What is on main |
| --- | --- |
| M0 | config + pinned deps (ADR 0001), strict schemas + registry, FastAPI app, `llm/client.py` seam, CI + governance + `.claude` hooks/skills |
| T01-T06 | invoice schema completeness; OpenAI Responses path (strict json_schema, env-priced cost); validation-retry (1 retry / 2 attempts); `POST /v1/extract`; FixtureClient + offline smoke; taxonomy handlers; `harness/normalize.py`; default provider = openai |
| T07 | **10 invoice fixtures flipped DRAFT -> REVIEWED** (PR #68, supersedes #36); harness finds 10 REVIEWED; `--live` scoring is the paid half (T17) |
| T08-T14 | job-posting completeness; Anthropic structured-output path + `default` routing; `api/idempotency.py` + SQLite store (WAL, first-writer-wins, 24h TTL) wired into the endpoint; full taxonomy coverage; PDF text via PyMuPDF (page/size caps, no OCR) |
| T16 / T18 | deterministic accuracy harness (`run_accuracy.py` + `scoring.py`, NO LLM judge, `--live`); per-run USD budget guard -> `budget_exceeded`; negative cap now fails loud (#66) |
| T19 | **Docker compose live** - image builds, `docker compose up` serves `/v1/extract`, healthcheck green (verified offline in fixture mode). README "Deploy (Docker)" section added |
| harness hardening | control-plane skip (#52); `--live` malformed-2xx / `--timeout` / misplaced-fixture (#57 items 2-4); corpus-wide misplaced-fixture validation (#63); `get_client` names the effective bad provider value (audit) |
| #28 / #29 | framework 404/405 carry taxonomy codes; taxonomy is a principle (one-code-per-non-200; `api/errors.py` is the source of truth; new codes need owner approval) |
| #21 / #25 / #38 | 5xx provider-detail sanitization; XDR fail-loud; gateway half-config fails loud (both providers) |

Locked architecture: the seam is text-based (`complete(json_schema) -> raw JSON text`,
re-validated by the retry loop); `llm/` never imports `api/`; `cost_usd` is env-priced (no
silent default that would mis-bill); retry = 1 retry / 2 attempts.

## Next up (gated on Chris labels / paid runs)

Most of the published-numbers path is merged; what remains is chiefly Chris's labels + paid runs,
plus two small code changes that land WITH T17 (the #46 null-handling / hallucination-denominator
metric and #57 item 1's `cost_usd` in the 422 body) - do not spend paid runs before those land:

- **T15** more labeled fixtures (30-50 each doc type) - blocks on Chris's labels.
- **T17** two-provider accuracy table - needs T15 + paid `--live` runs; folds in the
  null-handling / hallucination-denominator metric (#46) and the failed-422 cost fold (#57 item 1,
  contract pre-approved: add `cost_usd` to the 422 body).
- **T20** README with measured numbers - follows T17 (replaces the "Numbers pending" block).
- **T21** gateway-readiness trace - needs a `--live` run around the `LLM_BASE_URL` flip.

## Owner decisions taken this session (2026-07-03)

Chris directed "take a stance yourself and call the shots". Recorded stances:

- **#66** (budget negative cap): FIXED - a finite negative `EXTRACT_BUDGET_USD` now fails loud
  (was silently disabling the money guard), restoring parity with `llm/client._float_env_required`.
- **#35 / #54** (invoice model limits: nullable subtotal, total-level shipping): defer to a
  coordinated **invoice.v2**, not piecemeal v1 schema edits. Kept open, labelled v2.
- **#42** (idempotency atomic reservation): the sequential contract is correct + tested for the
  sync-only v1 scope; concurrency reservation is a documented future refinement. Kept open.
- **#32** (degrade-branch masks non-404/405 as 500): unreachable today (a wrong Content-Type is a
  422, not a 415); do NOT add a speculative ErrorCode. Kept open as a tripwire for when a new
  HTTPException path is added.
- **#13** (hook hardening): will NOT be auto-edited - these are the agent's own safety hooks;
  left for Chris's direct review.
- **#10** (ISO-4217 refresh): low-urgency maintenance (snapshot is recent). Kept open.
- **#6** (uv.lock / frozen CI): now actionable - `uv` is not on the Windows dev PATH but is
  pip-installable (`pip install uv` -> uv 0.11.26), and CI (Linux) has it. Generating `uv.lock` +
  switching CI to a frozen install is a clean follow-up slice.

## Open tracked issues

- **#6** commit `uv.lock` + frozen CI install (uv is pip-installable; now actionable).
- **#10** periodic ISO-4217 refresh (external data).
- **#13** hook-hardening backlog (sensitive: edits the agent safety hooks).
- **#32** degrade-branch masks future non-404/405 HTTPExceptions (owner taxonomy call; unreachable today).
- **#35** nullable `subtotal_minor` for total-only invoices (invoice.v2).
- **#42** idempotency atomic reservation under concurrency (sequential contract is correct for v1).
- **#46** hallucination-rate / null-handling denominator (folded into T17).
- **#54** v1 invoice cannot represent total-level shipping/adjustment (invoice.v2).
- **#57** `--live` accuracy-harness hardening; item 1 (fold a failed-validation 422's billed spend
  into cost totals) stays open, contract pre-approved, lands with T17.
- **#59** Dependabot: anthropic `<0.113` bump (CI-green; awaiting merge).

## Operating notes

See `docs/agentic/GIT_WORKFLOW.md`: the safety hook blocks command strings that *describe*
destructive patterns (use `-F` files), run the full gate before every push, and the
stacked-merge flow under strict protection. The local, git-excluded `ORCHESTRATOR.md` is the
live working log. Docker + the MCP toolset are available in this environment.
