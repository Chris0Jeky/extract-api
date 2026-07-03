# Backlog

Half-day tasks with definitions of done (DoD), sequenced M1-M4. A task is done
when its DoD is true and `make ci-quick` is green. Every task ships as its own PR
under the 5-part merge gate (AGENTS.md): two adversarial reviews, all threads
resolved, green CI, aged, with a newer PR above it. Small conventional commits.

## M0 - kickoff (DONE)

- [x] **T00 Scaffold + config + stubs.** pyproject (pinned, ADR 0001), Makefile,
  Dockerfile, compose, `.env.example`; FastAPI app with real `/healthz` and a
  stubbed extract endpoint; behavior modules raise `NotImplementedError`.
- [x] **T0G Governance + harness.** CI (ruff + mypy strict + pytest +
  fixtures-validate + gitleaks), dependabot + auto-merge, PR template, CODEOWNERS;
  `.claude` hooks + skills with `make test-hooks`; AGENTS.md + CONTRIBUTING +
  agentic/ops/testing docs.
- [x] **Schemas (real).** Strict `invoice.v1`, `job_posting.v1`, registry;
  null-union optionals; ISO-4217 + salary cross-field validators.
- [x] **Docs.** PLAN + ADRs 0001-0004; README v0; product CLAUDE.md.
- [x] **10 DRAFT invoice fixtures** + `fixtures-validate`. (Awaiting Chris to
  review and flip to REVIEWED.)

## M1 - invoice path end-to-end (10 fixtures passing)

- [x] **T01 Invoice schema completeness + tests.** (PR #7) Committed ISO-4217
  membership set + ASCII gate, cross-field total/subtotal validators, explicit-null
  required-but-nullable keys, empty-`[]` rejection; edge-case tests.
- [x] **T02 `llm/client.py` OpenAI structured-output path.** (PR #11) `responses.create`
  with strict json_schema; refusal/truncation/failed/empty mapped to `llm.errors.*`;
  `cost_usd` (env-priced) + `latency_ms`; schema sanitization (`llm/schema_utils`);
  mocked-SDK tests. NOTE: the seam stays text-based (returns JSON text), so it uses
  `responses.create`, not `parse` (ADR 0002 note).
- [x] **T03 Validation-retry loop.** (PR #12) `llm/pipeline.py:run_extraction`: attempt
  1 validate; on `ValidationError` attempt 2 appends the failure list + the previous
  response; second failure -> `ExtractionFailed` (JSON-safe trail) for the 422; usage
  accumulated across attempts; every retry logged with its kinds; first-fail-then-pass
  + both-fail + provider-error-passthrough tested. (1 retry / 2 attempts.)
- [x] **T04 `POST /v1/extract` happy path (invoice, OpenAI).** (PR #23) endpoint returns
  200 with `data` + full `meta`; integration test against a stubbed client.
- [x] **T04b Fixture/mock provider + `make smoke` extraction.** (PR #24) FixtureClient
  returns canned structured output; `make smoke` POSTs a known fixture and asserts
  the validated record + a forced 422, offline. (Extended in T12 with idempotency.)
- [x] **T05 `api/errors.py` taxonomy wiring.** (PR #30) full taxonomy -> HTTP rendering in
  the live app; tests assert each member renders the right status+body. Added the
  owner-approved `internal_error` (500) member + RequestValidationError + catch-all handlers.
- [x] **T06 `harness/normalize.py`.** (PR #26) date->ISO and money->minor-units with a
  currency minor-digit table; tests on GBP/USD/JPY (0 digits) and bad input
  raising, not coercing.
- [x] **T07 Flip 10 invoice fixtures to REVIEWED + passing.** (PR #68, supersedes #36)
  All 10 flipped DRAFT -> REVIEWED; `fixtures-validate` + the corpus-wide placement check
  (#63) pass; the harness finds 10 REVIEWED. The `accuracy-run` scoring half is the paid
  `--live` run (T17). Review-thread dispositions (0006 inferred line item kept; 0007/0008
  total-only subtotal = #35) recorded on #68.

## M2 - job-posting path + idempotency + full taxonomy

- [x] **T08 Job-posting schema completeness + tests.** (PR #31) enum + cross-field edge
  tests (the `competitive` and inverted-range cases); explicit-null keys + salary
  currency-when-present (closed #4, #8). Base model existed from M0.
- [x] **T09 `llm/client.py` Anthropic path.** (PR #37) structured output behind the seam
  via the modern Anthropic structured-outputs API (native `json_schema`, mirror of T02),
  NOT the legacy `messages.parse`/strict-tool-fallback the DoD assumed; `stop_reason`
  refusal/`max_tokens` mapped; mocked-response test.
- [x] **T10 Provider selection + `default` routing.** (PR #39) `provider` selects the
  client; `default` resolves via env; test covers openai/anthropic/default end-to-end.
- [x] **T11 `api/idempotency.py` + SQLite store.** (PR #40) key+sha256 storage (WAL,
  first-writer-wins); replay on match (`replayed:true`, no model call); 409 on hash
  mismatch; 24h TTL (lazy expiry + `sweep()`); tests for replay, conflict, expiry.
- [x] **T12 Wire idempotency into the endpoint + extend smoke.** (PR #41) store checked
  before any model call; integration test for one-call-then-replayed and the 409;
  `make smoke` extended with the replay + 409 assertions.
- [x] **T13 Full error taxonomy coverage.** (PR #43) every taxonomy member reachable and
  tested; README taxonomy table rows exist (frequencies TBD until T17).
- [x] **T14 PDF text extraction (PyMuPDF).** (PR #44) base64 pdf -> `get_text()`; no OCR;
  oversized/garbled input handled loudly (page/size caps); test on a small text-based PDF.

## M3 - accuracy harness, both providers, table committed

- **T15 30-50 invoice + 30-50 job fixtures (50/50 real/synthetic, labeled).**
  DoD: ADR 0003 labeling; `fixtures-validate` passes; DRAFT excluded from scoring.
  (Blocks on Chris.)
- [x] **T16 `harness/run_accuracy.py` scoring.** (PR #45) per-field exact-match (after
  normalization), hallucinated-field rate; deterministic, no LLM judge; `--live` mode
  against the serving endpoint. Hardened since: control-plane skip (#52), malformed-2xx /
  `--timeout` / misplaced-fixture (#57 items 2-4), corpus-wide placement (#63).
  Null-handling-correctness rate is deferred to T17 (#46).
- **T17 Two-provider accuracy table + cost/latency.** DoD: markdown table in
  `evals/reports/` with per-field accuracy + hallucinated-field rate + cost +
  p50/p95 latency, per doc type per provider; re-runnable via `make accuracy-run`.
  (Blocks on paid `--live` runs; folds in #46 + #57 item 1.)
- [x] **T18 Budget guard.** (PR #50) per-run USD cap; exceeding it raises `budget_exceeded`
  (402, control-plane); check-before-spend + reconcile-after (incl. failed-call cost);
  test forces the cap. Negative-cap now fails loud (#66). Reserve-reconcile is a documented
  v1 simplification (concurrency overshoot bounded; #42).

## M4 - deploy + README with numbers

- [x] **T19 Compose service live.** (2026-07-03) image builds (`python:3.13-slim`);
  `docker compose up` serves `/v1/extract` (verified offline in fixture mode: /healthz 200,
  /v1/extract 200 + validated data); healthcheck green; `.env.example` complete, no secrets.
  README "Deploy (Docker)" section added.
- **T20 README with numbers.** DoD: the accuracy table's lead sentence replaces
  "Numbers pending"; taxonomy table with observed frequencies; non-goals; the
  heuristic-confidence note.
- **T21 Gateway-readiness evidence.** DoD: before/after trace of one golden
  extraction around the `LLM_BASE_URL` flip; `GATEWAY_BYPASS` documented;
  `cost_usd` confirmed emitted.

## Cut line

If hours overrun: ship invoices only (M1 + T16-T20 for invoice alone); job
postings become fixtures-ready follow-up; the accuracy table still publishes with
one doc type.
