# CLAUDE.md - extract-api (pre-kickoff bootstrap)

Status: PRE-KICKOFF. The M0 kickoff session has not run yet. This file is a
bootstrap that orients you to run it. The kickoff session will replace this
with the real product CLAUDE.md (build / test / typecheck commands plus the
session protocol).

## What this repo is

extract-api: a strict-schema LLM extraction service that turns documents into
validated structured data and reports per-field accuracy across two providers
(OpenAI and Anthropic). It fails loudly instead of silently coercing.

Positioning line for every README / title: "I make LLM systems cheap,
reliable, and provably valuable in production." Lead with measured numbers;
until they exist, carry the block "Numbers pending: measured, not promised."

## How to start (run the M0 kickoff)

1. Read `_handover/KICKOFF_PROMPT.md` and run it as the kickoff. It is
   self-contained: every locked decision and schema field list is inlined.
2. `_handover/HANDOVER.md` is the long-form briefing (rationale, repo facts,
   ADR proposals, milestones, the gateway hook). Read it for context.
3. `_handover/` is LOCAL ONLY (gitignored). Never commit or push its contents.
   It is the private build briefing; treat it as read-only reference.

PHASE 0 note: the kickoff prompt says "confirm the repo is empty." That check
is satisfied. The only pre-existing files are harness scaffolding (`.claude/`,
`.gitignore`, this bootstrap `CLAUDE.md`) and the gitignored `_handover/`
briefing. There is no product code. Proceed to verify dependency versions
against official docs, report your plan in 15 lines or fewer, and STOP for
approval before writing product files.

## Locked decisions (do not re-litigate; full detail in _handover/HANDOVER.md)

- Two doc types only: invoice and uk_job_posting. Versioned schemas
  (invoice.v1, job_posting.v1); version travels in request and response.
- Pydantic v2 strict models. Validation-retry loop, max 2 retries; attempt 2
  appends the exact failure list to the prompt; the second failure returns 422
  with the full failure trail. Never silently coerce. Log every retry with its
  error class.
- Error taxonomy enum, exactly one per non-200: validation_failed,
  low_confidence, unsupported_doc_type, provider_error, provider_timeout,
  budget_exceeded, idempotency_conflict.
- Idempotency: Idempotency-Key + sha256(payload) stored with the response;
  same key + same hash replays (no model call, replayed:true in meta); same
  key + different hash returns 409; TTL 24h.
- Synchronous API only (async job queue is a non-goal).
- Both providers behind one thin `llm/client.py` seam that reads LLM_BASE_URL
  and LLM_API_KEY from env. No other module imports a provider SDK.
- Deterministic accuracy harness; NO LLM judges anywhere. OCR is a non-goal
  (text and pre-extracted PDF text only, via pymupdf).
- Normalization: dates to ISO 8601; money to integer minor units plus ISO-4217
  currency; a genuinely-absent field is null, never a guessed value.

## Gateway forward-compat (do not skip)

- `llm/client.py` routes purely on `LLM_BASE_URL` + `LLM_API_KEY`, plus a
  `GATEWAY_BYPASS=1` escape hatch. In week 10 the gateway migration is just
  flipping those two env values onto the gateway with a virtual key (full
  rationale in `_handover/HANDOVER.md` section 12). Keeping this seam clean now
  is the whole reason extract-api is built before the gateway.
- Emit `cost_usd` per request from day one; the gateway later surfaces "cost
  per accepted extraction" as a dashboard view.

## Hard rules

- No secrets in any file. Env references only; ship `.env.example`.
- No em dashes anywhere in the repo.
- Conventional commits. Kickoff work goes on branch `chore/kickoff`.
- No push without explicit approval. No GitHub remote is set yet.
- Never commit or push anything under `_handover/`.
- End every working session with a report: done / decisions needed / next
  unblocked tasks.
