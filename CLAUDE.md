# CLAUDE.md - extract-api

extract-api is a strict-schema LLM extraction service that turns documents into
validated structured data and reports per-field accuracy across two providers
(OpenAI and Anthropic). It fails loudly instead of silently coercing.

Positioning line for every README / title / CV line: "I make LLM systems cheap,
reliable, and provably valuable in production." Lead with measured numbers; until
they exist, carry "Numbers pending: measured, not promised."

`AGENTS.md` is the rulebook (Review Policy, Definition of Done, the 5-part merge
gate). This file is orientation, commands, and locked decisions. Read both before
changing code.

## Commands

```
uv venv --python 3.13 && uv pip install -e ".[dev]"   # setup (fallback: python3 -m venv .venv)
make help          # list targets
make dev           # run the API (uvicorn on :8200; /docs for OpenAPI)
make test          # pytest + coverage (ratchet floor in pyproject)
make typecheck     # mypy strict
make lint          # ruff check + format check
make ci-quick      # lint + typecheck + test (pre-push gate)
make smoke         # deterministic offline smoke (no paid model calls)
make fixtures-validate   # validate fixtures against their schema + labels
make accuracy-run        # accuracy harness (pending M3)
make test-hooks    # self-test the agent safety hooks
```

On Windows pass the venv interpreter, e.g. `make PYTHON=.venv/Scripts/python test`.

## Session protocol

1. Read this file, `AGENTS.md`, and `tasks/BACKLOG.md`.
2. State the next unblocked task and wait for the go.
3. Work one safe slice (`.claude/skills/safe-slice`); small conventional commits
   (`<area>: <imperative summary>`); behavior changes ship with tests.
4. End every session with a report: done / decisions needed / next unblocked
   tasks (use `.claude/skills/verify-and-sync`).

## Locked decisions (do not re-litigate; full detail in docs/plan/PLAN.md)

- Two doc types only: `invoice`, `uk_job_posting`. Versioned schemas
  (`invoice.v1`, `job_posting.v1`); version travels in request and response.
- Pydantic v2 strict models. Validation-retry loop, max 1 retry (2 attempts
  total); attempt 2 appends the exact failure list; second failure returns 422 with
  the full trail. Never silently coerce. Log every retry with its error class.
- Error taxonomy: exactly one ErrorCode per non-200. The enum in `api/errors.py` is the
  single source of truth; new members require owner approval (do not add casually). What
  is locked is the one-code-per-non-200 invariant, not a frozen count. Current members:
  `validation_failed`, `low_confidence`, `unsupported_doc_type`, `provider_error`,
  `provider_timeout`, `budget_exceeded`, `idempotency_conflict`, `internal_error` (T05),
  `not_found` (issue #28), `method_not_allowed` (issue #28).
- Idempotency: `Idempotency-Key` + `sha256(payload)`; same key+hash replays
  (`replayed:true`, no model call); same key+different hash returns 409; TTL 24h.
  SQLite store (ADR 0004).
- Synchronous API only (async job queue is a non-goal).
- Both providers behind one `llm/client.py` seam reading `LLM_BASE_URL` +
  `LLM_API_KEY` (+ `GATEWAY_BYPASS`). No other module imports a provider SDK.
- Structured outputs guarantee SHAPE, not SEMANTICS (ADR 0002): optionals are
  null-unions; cross-field / normalization / value constraints are Pydantic
  validators after parse; that is what the retry loop catches.
- Deterministic accuracy harness; NO LLM judges anywhere. OCR is a non-goal
  (text and pre-extracted PDF text only, via PyMuPDF).
- Normalization: dates to ISO 8601; money to integer minor units + ISO-4217
  currency; a genuinely-absent field is `null`, never a guessed value.
- Emit `cost_usd` per request from day one (gateway forward-compat).

## Build state

M0 + M1's T01-T03 are merged to `main` (see `docs/STATUS.md` for the full handoff):

- M0 kickoff: config + pinned deps (ADR 0001), CI + governance + `.claude` harness,
  10 DRAFT invoice fixtures.
- T01: invoice schema completeness (committed ISO-4217 membership, cross-field
  total/subtotal validators, explicit-null required-but-nullable keys).
- T02: the `llm/client.py` OpenAI path (Responses API + strict json_schema,
  `llm/errors.py`, `llm/schema_utils.py` sanitization, fail-loud, env-priced cost).
- T03: the validation-retry pipeline (`llm/pipeline.py:run_extraction`, 1 retry).

So the invoice pipeline is built end-to-end EXCEPT the HTTP wiring. NEXT: T04
(`POST /v1/extract` happy path) + T04b (FixtureClient + offline smoke), then T05
(taxonomy wiring) and T06 (normalize) to finish M1. See `tasks/BACKLOG.md` and the
open issues (#4-#13) for the tracked follow-ups.

## NEVER DO

- Silently coerce, or guess a value for an absent field (return `null` or fail
  loudly).
- Import a provider SDK outside `llm/client.py`.
- Use an LLM judge in the accuracy harness.
- Add a doc type beyond `invoice` + `uk_job_posting` in v1.
- Commit secrets (env refs only; document in `.env.example`).
- Put an em dash anywhere in the repo.
- Push without explicit approval, or self-merge a PR.

## Repo facts

- Remote: `github.com/Chris0Jeky/extract-api` exists and is authed (an earlier
  bootstrap note said no remote was set; corrected here).
- Kickoff work is on branch `chore/kickoff`. Conventional commits.
