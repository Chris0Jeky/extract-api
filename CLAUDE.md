# CLAUDE.md - extract-api

Strict-schema LLM extraction service: document text (or PDF text) in, Pydantic v2
strict record out, with deterministic accuracy scoring for OpenAI and Anthropic.
It fails loudly instead of silently coercing. The served paths and scorer are
implemented; human fixture review and paid provider measurements remain open
(`tasks/BACKLOG.md` T15/T17/T20/T21). The #46 metrics are implemented: exact null
matches earn exact-match credit; hallucination and null-handling correctness use
expected-null opportunities in usable, schema-valid predictions, are complementary,
and report `n/a` when there are none. Failed records earn no exact-match credit;
their expected-null fields are counted separately as exclusions from these
conditional null metrics. Terminal 422 bodies expose `cost_usd`, and reports split
successful/failed spend, labelling unknown failed spend from older servers.

Positioning line for every README / title / CV line: "I make LLM systems cheap,
reliable, and provably valuable in production." Lead with measured numbers; until
they exist, carry "Numbers pending: measured, not promised."

**Authority: T2** (`.agent-harness/tier.json`) - push and merge free behind global
law 2's gate. Review and merge policy lives once, in `~/.claude/rules/laws.md` (the
twelve laws, auto-injected); do not restate it here. `AGENTS.md` holds the
Definition of Done and the repo review lenses; `tasks/BACKLOG.md` is both the task
list and the human-action file (only Chris ticks its human-blocked items);
`docs/STATUS.md` is the narrative handoff (check its date before trusting it).

## Map

| Region | What lives there | Its tests |
| --- | --- | --- |
| `api/` | FastAPI app (`main.py` `create_app`, `/readyz`, the `ExtractAdmission` cap), caller keys (`auth.py`), taxonomy rendering (`errors.py`), SQLite idempotency with store identity, budget guard, PDF/text decode (`content.py`), JSON logs and request ids (`observability.py`) | `test_api`, `test_caller_auth`, `test_extract_endpoint`, `test_errors`, `test_idempotency`, `test_budget`, `test_content`, `test_readiness`, `test_replica_guard`, `test_concurrency`, `test_observability`, `test_uvicorn_logging` |
| Hosting | `Dockerfile` + `docker-entrypoint.sh`, `render.yaml`, `railway.json`, `.github/workflows/image.yml` (build, scan, attest) and `deploy.yml` (dispatch-only digest deploy), `.hosting/manifest.json` (agent-hq manifest v2), `docs/ops/` (RUNBOOK, SIZING, OBSERVABILITY), ADRs 0004-0005 | `test_deploy_descriptors`, `test_workflows`; `scripts/docker_persistence_smoke.py` and `scripts/load_test.py` in CI |
| `llm/` | The only provider seam. `client.py` (both SDKs), `pipeline.py:run_extraction` (validation-retry), `schema_utils`, `prompts`, `errors` | `test_llm_client`, `test_openai_client`, `test_anthropic_client`, `test_pipeline`, `test_schema_utils`, `test_prompts`, `test_import_boundary` |
| `schemas/` | Strict `invoice.v1` + `job_posting.v1`, ISO-4217 set, `registry.py` | `test_schemas`, `test_iso4217`, `test_registry` |
| `harness/` | Deterministic accuracy scoring (`run_accuracy.py`, `scoring.py`) | `test_run_accuracy`, `test_scoring` |
| `fixtures/` | 10 REVIEWED invoices, 20 DRAFT invoices, and 20 DRAFT job postings; DRAFT is excluded from scoring and job-posting accuracy runs still have no REVIEWED input | `test_validate_fixtures` |
| `.claude/hooks/dispatch.py` | Vendored canonical deny floor, not wired by committed settings. T4-class in any repo: do not edit | `.claude/hooks/smoke_test.py` |

`llm/` never imports `api/`. Only `llm/client.py` may import a provider SDK, and
`tests/test_import_boundary.py` enforces that repo-wide, `scripts/` included.

## Proving checks

Install the locked development environment with `uv sync --locked --extra dev`.
Use `uv run` so commands use that environment.

| Changed | Narrowest check |
| --- | --- |
| anything | `uv run make lint` |
| one seam | `uv run python -m pytest --no-cov tests/test_<area>.py` |
| any typed source | `uv run make typecheck` |
| endpoint, wiring, idempotency | `uv run make smoke` (offline 200, forced 422, replay, and 409) |
| fixtures or labels | `uv run make fixtures-validate` |
| accuracy orchestration | `uv run make accuracy-rehearsal` (REVIEWED label echo through the API, zero provider cost) |
| floor bytes or their pin/checker/gate | `uv run make test-floor` (integrity check, then the canonical matrix) |
| `scripts/agent_hooks/pre_tool_use.py` | `uv run make test-hooks` |
| `scripts/agent_hooks/pre_tool_use.py` or `post_tool_failure.py` | `uv run python -m pytest --no-cov tests/test_agent_hooks.py` |
| `scripts/agent_hooks/session_start.py` | `uv run python scripts/agent_hooks/session_start.py`; inspect its output |
| pre-push gate | `uv run make ci-quick` (floor integrity, lint, mypy, and full pytest coverage) |

CI (`.github/workflows/ci.yml`) also validates fixtures and runs gitleaks on
Python 3.13. Use the current PR checks for test counts and coverage evidence;
rehearsal results do not measure provider accuracy.

## Pitfalls

- **Targeted pytest slices need `--no-cov`.** The full-suite coverage floor in
  `pyproject.toml` is `--cov-fail-under=95`; a passing slice can fail that global
  threshold. Keep coverage enabled for the full run. The floor may rise, never fall.
- `.agent-harness/floor-integrity.json` pins the verified upstream commit and both
  vendored SHA-256 digests. `check-floor` and ordinary CI verify raw bytes without
  executing hooks; existing `.gitattributes` keeps Python checkouts LF on Windows.
- The large `.claude/hooks/smoke_test.py` matrix stays outside `ci-quick`. Run it
  only for authorized floor or integrity/gate changes; `.github/workflows/floor.yml`
  applies those path filters and runs on Linux and Windows with 15-minute budgets.
  When syncing the floor, verify upstream bytes before updating the pin. These
  checks do not establish runtime activation; committed settings remain unwired.
- `scripts/agent_hooks/pre_tool_use.py` is a **deprecated** bespoke floor, no
  longer wired; its retirement is tracked as issue #83. Leave it alone.
- Use `uv run make test` to select the locked environment; on Windows, an explicit
  `PYTHON=.venv/Scripts/python` override is also available.
- `ruff` skips `.claude/hooks` by design (vendored canonical bytes).
- `ORCHESTRATOR.md` at the repo root is a local-only working log, git-excluded via
  `.git/info/exclude`. Never commit it.

## Locked decisions (do not re-litigate; detail in docs/plan/PLAN.md + docs/adr/)

- Two doc types only: `invoice`, `uk_job_posting`. Versioned schemas
  (`invoice.v1`, `job_posting.v1`); the version travels in request and response.
- Validation-retry: max 1 retry (2 attempts). Attempt 2 appends the exact failure
  list; a second failure returns 422 with the full trail. Never silently coerce.
  Log every retry with its error class.
- Exactly one `ErrorCode` per non-200. `api/errors.py` is the single source of
  truth; new members need owner approval. The invariant is locked, not the count.
  `unauthorized` (401) was approved by owner decision `extract-api-caller-auth` (2026-10-10).
- Caller auth: `Authorization: Bearer <key>` on every path except `/healthz` and `/readyz`
  (`api/auth.py` `is_open_path`, shared with `ExtractAdmission`; guard by default, never an
  allowlist of guarded paths: `/v1/extract%0A` once bypassed one). A middleware outside `ExtractAdmission`. The service stores SHA-256 hashes only, in
  `EXTRACT_API_KEY_SHA256S` (comma separated, several valid at once). No hash set means
  `/v1/extract` fails closed with 500 `internal_error`. Never log a token or a hash.
  `/readyz` exposes startup-captured `caller_auth_configured`; deployment requires
  literal `true` and a keyless `/v1/extract` probe returning 401. Its invalid `{}`
  body prevents provider work if the auth check regresses.
- Idempotency: `Idempotency-Key` + `sha256(payload)`; same key+hash replays
  (`replayed:true`, no model call); same key+different hash is 409; TTL 24h;
  SQLite (ADR 0004). This is a sequential replay contract; concurrent in-flight
  deduplication remains deferred in #42.
- Structured outputs guarantee SHAPE, not SEMANTICS (ADR 0002): cross-field and
  value constraints are Pydantic validators after parse, which is what the retry
  loop catches. The seam is text-based: `complete(json_schema)` returns raw JSON
  text, re-validated by the loop. Both providers read `LLM_BASE_URL` +
  `LLM_API_KEY` (+ `GATEWAY_BYPASS`), so the gateway move is an env change.
- Normalization: dates to ISO 8601; money to integer minor units + ISO-4217
  currency; a genuinely absent field is `null`, never a guess.
- `cost_usd` is emitted per request, env-priced, with no silent default that could
  mis-bill.
- Non-goals: async job queue, OCR (text and pre-extracted PDF text only, via
  PyMuPDF), LLM judges anywhere in the accuracy harness.

## NEVER DO

- Silently coerce, or guess a value for an absent field (return `null` or fail loudly).
- Import a provider SDK outside `llm/client.py`.
- Use an LLM judge in the accuracy harness.
- Add a doc type beyond `invoice` + `uk_job_posting` in v1.
- Commit secrets (env refs only; document in `.env.example`).
- Put an em dash anywhere in the repo.
