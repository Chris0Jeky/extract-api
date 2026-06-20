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
- **T04 `POST /v1/extract` happy path (invoice, OpenAI).** DoD: endpoint returns
  200 with `data` + full `meta`; integration test against a stubbed client.
- **T04b Fixture/mock provider + `make smoke` extraction.** DoD: FixtureClient
  returns canned structured output; `make smoke` POSTs a known fixture and asserts
  the validated record + a forced 422, offline. (Extended in T12 with idempotency.)
- **T05 `api/errors.py` taxonomy wiring.** DoD: full taxonomy -> HTTP rendering in
  the live app; tests assert each member renders the right status+body. (Enum +
  mapping + handlers already exist from M0.)
- **T06 `harness/normalize.py`.** DoD: date->ISO and money->minor-units with a
  currency minor-digit table; tests on GBP/USD/JPY (0 digits) and bad input
  raising, not coercing.
- **T07 Flip 10 invoice fixtures to REVIEWED + passing.** DoD: human-cleared
  labels; `make accuracy-run` scores invoice/OpenAI and all 10 match. (Blocks on
  Chris.)

## M2 - job-posting path + idempotency + full taxonomy

- **T08 Job-posting schema completeness + tests.** DoD: enum + cross-field edge
  tests (the `competitive` and inverted-range cases). Base model exists from M0.
- **T09 `llm/client.py` Anthropic path (`messages.parse`).** DoD: structured
  output behind the seam; `stop_reason` refusal/`max_tokens` mapped; strict-tool
  fallback stubbed; mocked-response test.
- **T10 Provider selection + `default` routing.** DoD: `provider` selects the
  client; `default` resolves via env; test covers all three. (Routing exists from
  M0; this wires it into the pipeline.)
- **T11 `api/idempotency.py` + SQLite store.** DoD: key+sha256 storage; replay on
  match (`replayed:true`, no model call); 409 on hash mismatch; 24h TTL sweep;
  tests for replay, conflict, expiry.
- **T12 Wire idempotency into the endpoint + extend smoke.** DoD: store checked
  before any model call; integration test for one-call-then-replayed and the 409;
  `make smoke` extended with the replay + 409 assertions.
- **T13 Full error taxonomy coverage.** DoD: every taxonomy member reachable and
  tested; README taxonomy table rows exist (frequencies TBD).
- **T14 PDF text extraction (PyMuPDF).** DoD: base64 pdf -> `get_text()`; no OCR;
  oversized/garbled input handled loudly; test on a small text-based PDF.

## M3 - accuracy harness, both providers, table committed

- **T15 30-50 invoice + 30-50 job fixtures (50/50 real/synthetic, labeled).**
  DoD: ADR 0003 labeling; `fixtures-validate` passes; DRAFT excluded from scoring.
  (Blocks on Chris.)
- **T16 `harness/run_accuracy.py` scoring.** DoD: per-field exact-match (after
  normalization), null-handling correctness, hallucinated-field rate;
  deterministic, no LLM judge; `--live` mode against the serving endpoint.
- **T17 Two-provider accuracy table + cost/latency.** DoD: markdown table in
  `evals/reports/` with per-field accuracy + hallucinated-field rate + cost +
  p50/p95 latency, per doc type per provider; re-runnable via `make accuracy-run`.
- **T18 Budget guard.** DoD: per-run USD cap (reuse Hero 1 reserve-reconcile);
  exceeding it raises `budget_exceeded`; test forces the cap.

## M4 - deploy + README with numbers

- **T19 Compose service live.** DoD: image builds; `docker compose up` serves
  `/v1/extract`; healthcheck green; `.env.example` complete, no secrets.
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
