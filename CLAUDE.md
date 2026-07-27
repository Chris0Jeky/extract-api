# CLAUDE.md - extract-api

Strict-schema LLM extraction service: document text (or PDF text) in, Pydantic v2
strict record out, per-field accuracy reported across OpenAI and Anthropic. It
fails loudly instead of silently coercing. ~2.7k lines of source, 323 tests, 99%
coverage; engineering-complete through M3 and deployable. What is left is human
fixture labels plus paid `--live` runs (`tasks/BACKLOG.md` T15/T17/T20/T21).

Positioning line for every README / title / CV line: "I make LLM systems cheap,
reliable, and provably valuable in production." Lead with measured numbers; until
they exist, carry "Numbers pending: measured, not promised."

**Authority: T2** (`.agent-harness/tier.json`) - push and merge free on green
proving checks. Review and merge policy lives once, in `~/.claude/CLAUDE.md` (the
twelve laws, auto-injected); do not restate it here. `AGENTS.md` holds the
Definition of Done and the repo review lenses; `tasks/BACKLOG.md` is both the task
list and the human-action file (only Chris ticks its human-blocked items).

## Map

| Region | What lives there | Its tests |
| --- | --- | --- |
| `api/` | FastAPI app (`main.py` `create_app`), taxonomy rendering (`errors.py`), SQLite idempotency, budget guard, PDF/text decode (`content.py`) | `test_api`, `test_extract_endpoint`, `test_errors`, `test_idempotency`, `test_budget`, `test_content` |
| `llm/` | The only provider seam. `client.py` (both SDKs, 467 lines), `pipeline.py:run_extraction` (validation-retry), `schema_utils`, `prompts`, `errors` | `test_llm_client`, `test_openai_client`, `test_anthropic_client`, `test_pipeline`, `test_schema_utils`, `test_prompts`, `test_import_boundary` |
| `schemas/` | Strict `invoice.v1` + `job_posting.v1`, ISO-4217 set, `registry.py` | `test_schemas`, `test_iso4217`, `test_registry` |
| `harness/` | Deterministic accuracy scoring (`run_accuracy.py`, `scoring.py`) and `normalize.py` | `test_run_accuracy`, `test_scoring`, `test_normalize` |
| `fixtures/` | 10 REVIEWED invoices, 1 job posting; DRAFT is excluded from scoring | `test_validate_fixtures` |
| `.claude/hooks/dispatch.py` | Vendored canonical deny floor (v1.6.20). T4-class in any repo: do not edit | `.claude/hooks/smoke_test.py` |

`llm/` never imports `api/`. Only `llm/client.py` may import a provider SDK, and
`tests/test_import_boundary.py` enforces that repo-wide, `scripts/` included.

## Proving checks (measured 2026-07-27 on Windows)

Use the venv interpreter: `make PYTHON=.venv/Scripts/python <target>`, or call the
module directly as below.

| Changed | Narrowest check | Measured |
| --- | --- | --- |
| anything | `python -m ruff check . && python -m ruff format --check .` | 0.5s, clean |
| one seam | `python -m pytest --no-cov tests/test_<area>.py` | <1s |
| any typed source | `python -m mypy` | 10s cold / 1s warm, 23 files clean |
| endpoint, wiring, idempotency | `python scripts/smoke.py` | 0.8s: boots the app, 200 + forced 422 + replay + 409, offline |
| fixtures or labels | `python scripts/validate_fixtures.py` | 0.3s, "10 REVIEWED, 0 DRAFT" |
| `scripts/agent_hooks/*` | `make test-hooks` | 0.1s, 23 denies + 13 allows |
| pre-push gate | `make ci-quick` (lint + mypy + pytest) | 20s cold / 6s warm, 323 passed, coverage 99.39% |

CI (`.github/workflows/ci.yml`) runs exactly that plus `validate_fixtures.py` and
gitleaks, on Python 3.13. There is no extra lint config to satisfy.

## Pitfalls (measured here, not guessed)

- **A targeted pytest slice fails on coverage, not on your test.** `addopts` in
  `pyproject.toml` carries `--cov-fail-under=70`, so `pytest tests/test_schemas.py`
  reports 12% and exits 1 with all 27 tests passing. Add `--no-cov` to any slice;
  drop it for the full run. The floor is a ratchet: it may rise, never fall.
- `.claude/hooks/smoke_test.py` is the floor's own matrix: **2232 cases, 5m15s on
  this box** (one subprocess per case). It is not in CI or `ci-quick`. Run it only
  when the floor changes, which is T4-class work you should not be doing here.
- `scripts/agent_hooks/pre_tool_use.py` is a **deprecated** bespoke floor, no
  longer wired; its retirement is tracked as issue #83. Leave it alone.
- Windows: bare `make test` picks the wrong interpreter. Pass `PYTHON=`.
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
- Idempotency: `Idempotency-Key` + `sha256(payload)`; same key+hash replays
  (`replayed:true`, no model call); same key+different hash is 409; TTL 24h;
  SQLite (ADR 0004).
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
