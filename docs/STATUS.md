# STATUS - where extract-api is

Living snapshot for starting a new session strong. Last updated 2026-06-20.
Authoritative detail lives in `AGENTS.md` (rules), `tasks/BACKLOG.md` (tasks),
`docs/plan/PLAN.md` + `docs/adr/` (decisions). This file is the orientation.

## Merged to `main` (gate-green, ~98% coverage)

M0 + M1's T01-T03 are merged. The invoice pipeline is built end-to-end **except the
HTTP wiring**.

| Slice | PR | What landed |
| --- | --- | --- |
| M0 | #1 | config + pinned deps (ADR 0001), strict schemas + registry, FastAPI app w/ `/healthz`, the `llm/client.py` seam, CI + governance + `.claude` hooks/skills, 10 DRAFT invoice fixtures |
| T01 | #7 | invoice schema completeness: `schemas/iso4217.py` membership set, ASCII currency gate, cross-field validators (`total == subtotal + tax`; `subtotal == sum(line amounts)`), explicit-null required-but-nullable keys, empty-`[]` rejection |
| T02 | #11 | OpenAI path: `responses.create` + strict json_schema, `llm/errors.py` (Provider* exceptions), `llm/schema_utils.py` (sanitize to provider subset), fail-loud on refusal/truncation/failed/empty, env-priced `cost_usd`, `latency_ms`, bounded timeout, `GATEWAY_BYPASS` routing |
| T03 | #12 | `llm/pipeline.py:run_extraction` - call -> strict validate -> 1 feedback retry (prev response + error summary) -> `ExtractionFailed` (JSON-safe trail) on 2nd fail; usage accumulated; retries logged |

Key architecture decisions made during the build:
- The seam is **text-based**: `complete(json_schema) -> raw JSON text`; the retry loop
  re-validates. So OpenAI uses `responses.create` (not `parse`). (ADR 0002 note.)
- **Layering**: `llm/` never imports `api/`. The client raises `llm.errors.Provider*`;
  the API layer (T04) maps them to the `api/errors.py` taxonomy.
- **Cost** is computed from REQUIRED env per-token prices (no silent default that
  would mis-bill); a gateway may supply cost later.
- **Retry = 1 retry / 2 attempts** (confirmed by Chris).

## Next up (finish M1)

1. **T04** `POST /v1/extract` happy path: wire `get_client` + `run_extraction` into
   `api/main.py`; build `data` + full `meta` (incl. heuristic `field_confidence`,
   `cost_usd`, `latency_ms`); map `ExtractionFailed`/`Provider*` -> taxonomy; new
   `llm/prompts.py` for the system prompt. Integration test via FixtureClient.
2. **T04b** `FixtureClient.complete` returns canned text; `make smoke` POSTs a fixture
   offline and asserts the record + a forced 422.
3. **T05** taxonomy wiring: add a `RequestValidationError` handler so an unknown
   `doc_type` renders `unsupported_doc_type` (closes #5).
4. **T06** `harness/normalize.py`: date->ISO, money->minor-units (currency digit table).

Then M2 (job-posting + idempotency), M3 (accuracy harness + two-provider table),
M4 (deploy + README numbers). See `tasks/BACKLOG.md`.

The T02-T05 architecture blueprint (from a code-architect pass) is summarized in the
local `ORCHESTRATOR.md` if more detail is needed.

## Open tracked issues

- **#4 + #8** (T08, M2): JobPostingV1 needs explicit-null required-but-nullable keys
  and a `salary_currency`-when-present check (mirrors the invoice T01 change). Until
  then job_posting's schema is not OpenAI-strict-valid; invoice is.
- **#5** (T05): unsupported `doc_type` must render the taxonomy, not FastAPI's 422.
- **#6**: commit `uv.lock` + switch CI to a frozen install (ADR 0001 hardening).
- **#9** (T02/T09): provider json-schema sanitization edge cases.
- **#10**: periodic ISO-4217 refresh / currency-status audit.
- **#13**: hook-hardening backlog (obscure destructive-command bypass variants).

## Known bug

`.github/workflows/dependabot-auto-merge.yml` job FAILS (non-required check; GitHub
native auto-merge covers it). Fix it.

## Open questions for Chris

- **Q2**: only PR #1 was actually open at the last session's start (not "plenty"); the
  rest were generated as the stacked PRs. Confirm that matches intent.
- **Q3**: invoice line-item math - aggregate consistency is enforced (`total`,
  `subtotal == sum`), but NOT per-line `qty*price` (discounts/rounding make it unsafe
  in v1). Confirm, or ask to add it.
- **Q4**: flip the 10 DRAFT invoice fixtures to REVIEWED (T07) - blocks on your labels.

## Operating notes

See `docs/agentic/GIT_WORKFLOW.md` ("Agent operating notes"): the safety hook blocks
your own command strings that *describe* destructive patterns (use `-F` files), run
the full gate before every push, and the stacked-merge flow under strict protection.
