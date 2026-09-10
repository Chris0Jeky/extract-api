# extract-api: comprehensive review and acceleration plan

## 1. Review boundary

This review is pinned to `main` commit `aeacafa63685af3b47030375d13b2b5c1d5979f9` from 2026-09-03T00:34:33Z. It uses repository metadata, source files, issue bodies/comments, pull-request state and GitHub check results. It is a static review: the repository could not be cloned into the review environment, so local tests, coverage and runtime benchmarks were not independently rerun.

That distinction matters because the repository documentation claims roughly 323 tests and 99% coverage, while `pyproject.toml` currently enforces a 95% coverage floor. Treat the configured floor and observed CI results as current evidence; treat narrative counts in `CLAUDE.md` as claims to regenerate from the actual checkout.

## 2. Executive verdict

### What the project really is

`extract-api` is a **schema-first structured-output microservice and evaluation workload**. It accepts document text or text-bearing PDFs, routes them to OpenAI or Anthropic, requires output against a strict Pydantic schema, retries once with the precise validation failures, and returns either validated data or a deterministic error. It currently supports invoices and UK job postings.

The project is deliberately narrow:

- synchronous HTTP rather than a queue;
- two document types rather than arbitrary schema upload;
- no OCR;
- no LLM judge;
- no calibrated confidence;
- no built-in authentication or tenancy;
- gateway-oriented provider routing.

That narrowness is a strength. It makes the service inspectable and benchmarkable instead of becoming a general “document AI” platform before proving anything.

### What is already strong

The data plane is substantially complete. Strong observed choices include:

- strict Pydantic v2 models and forbidden unknown fields;
- an explicit two-attempt validation-retry loop;
- one provider abstraction with lazy OpenAI/Anthropic implementations;
- provider timeouts and bounded SDK retries;
- explicit per-model pricing configuration;
- deterministic error taxonomy;
- request/content size limits and no-OCR boundary;
- SQLite idempotency with persistent Docker volume;
- a process-local budget stop;
- deterministic offline smoke mode;
- strict Ruff and mypy settings;
- a 95% coverage gate;
- frozen `uv.lock` installs;
- non-root Docker runtime;
- Docker persistence smoke and secret scanning;
- a protected `main` branch.

This is much closer to a reference implementation than a toy API.

### What is not finished

The project’s central public promise is “measured, not promised,” yet the evidence plane is incomplete:

- only ten reviewed invoice fixtures exist;
- the job-posting directory has no reviewed fixtures;
- `evals/reports/` is empty apart from `.gitkeep`;
- failed validation spend is absent from reported totals;
- hallucination uses the wrong headline denominator;
- a failed extraction corrupts null-field accounting;
- nested `line_items` is scored as one opaque field;
- paid runs have no append-only journal or robust resume;
- manifests do not freeze prompt/schema/corpus/pricing/build identity;
- transport failures are not cleanly separated from model quality;
- several open issues describe states already fixed on `main`;
- multiple authority/status documents have drifted.

So the current maturity is **engineering-complete prototype, evidence-incomplete release candidate**.

### Recommended strategic identity

Near term, position the repository as:

> A reference-grade, strict-schema LLM extraction service with reproducible evaluation and release-gate evidence across providers.

Do not position it yet as a broadly differentiated SaaS. Generic extraction endpoints are easy to imitate; the valuable asset here is the combination of strict contracts, reproducible corpora, cost/reliability accounting and regression gating. The project becomes strategically stronger when used as one workload in a shared LLM Release Gate alongside other structured-output applications.

## 3. Maturity assessment

| Dimension | Score / 10 | Interpretation |
|---|---:|---|
| Core implementation | 8.2 | Major runtime paths exist and are deliberately bounded. |
| Engineering discipline | 8.7 | CI, typing, coverage, locking and container hygiene are unusually strong. |
| Benchmark integrity | 4.0 | Thoughtful foundation, but public metric semantics and run durability are unfinished. |
| Corpus readiness | 2.5 | 10 reviewed invoice fixtures; 0 reviewed job fixtures. |
| Operational readiness | 5.5 | Suitable behind a gateway on one host; not ready for direct public exposure. |
| Documentation coherence | 6.0 | Rich rationale, but several documents and issues have drifted. |
| Standalone product differentiation | 4.5 | Needs a domain wedge, review workflow or proprietary evidence advantage. |
| Platform/release-gate potential | 8.5 | Excellent fit for reusable regression evaluation. |

These are analytical judgments, not generated repository metrics.

## 4. Work completed and development evolution

The repository has evolved through a coherent sequence rather than random feature accumulation.

### Phase A: strict contract foundation

The first layer established:

- an API contract for `invoice.v1` and `uk_job_posting.v1`;
- strict Pydantic configuration;
- ISO-4217 validation;
- invoice cross-field arithmetic;
- a schema registry;
- provider-independent response metadata.

The important design instinct was to make post-parse semantic failures first-class. Provider-side JSON shape constraints are not treated as sufficient.

### Phase B: provider and validation reliability

The next layer added:

- OpenAI and Anthropic adapters behind `llm/client.py`;
- exact structured-output requests;
- two attempts with the previous output and validator errors fed back;
- provider timeouts and SDK retry caps;
- aggregate attempts/tokens/cost/latency;
- errors that preserve classification without exposing raw model output.

This is the core technical story of the project and is already credible.

### Phase C: API control and replay semantics

The service then gained:

- error-code standardisation;
- content limits and PDF text extraction;
- SQLite idempotency and 24-hour replay;
- same-key/different-payload conflicts;
- a process-local cost budget;
- deterministic offline fixture mode.

This moved it from “model wrapper” to a constrained service.

### Phase D: evidence harness

The repository added:

- reviewed-vs-DRAFT fixture governance;
- deterministic exact scoring;
- per-field output tables;
- null/hallucination concepts;
- live endpoint driving;
- control-plane skips;
- timeout and malformed response handling;
- paid-run preflight and report preservation.

Adversarial review then found that the evidence system itself needed product-level contracts. Recent work has increasingly focused on preventing paid evidence loss and misclassification. That is a healthy evolution: once the runtime stabilised, attention shifted from feature delivery to proof integrity.

### Phase E: agentic workflow and repository governance

The project also accumulated:

- `AGENTS.md` and `CLAUDE.md` authority guidance;
- a shared vendored deny floor;
- T2 harness declaration;
- issue-driven adversarial review;
- Dependabot and auto-merge support;
- relicensing documentation.

This layer is useful but has become disproportionately complex relative to the small application. Several open issues concern the agent harness rather than product behavior. The right correction is not to remove governance; it is to centralise shared safety logic and keep repo-local evidence lightweight.

## 5. Current architecture

### Data plane

```text
POST /v1/extract
  -> request model validation
  -> schema registry resolve(doc_type, version)
  -> text/PDF content extraction + size guards
  -> process budget pre-check
  -> provider client resolution from environment
  -> generic prompt + provider strict schema
  -> attempt 1
       -> JSON decode + Pydantic semantic validation
       -> retry with exact failures when invalid
  -> attempt 2 or success
  -> process budget reconciliation
  -> response/error taxonomy
  -> optional SQLite idempotency replay/store
```

The architecture is intentionally synchronous and compact. Keep it that way through the first measured release.

### Evidence plane

```text
REVIEWED fixture files
  -> corpus preflight
  -> sequential live HTTP requests
  -> response/error classification
  -> top-level field scoring
  -> in-memory aggregation
  -> Markdown report
```

This plane is the current weak point. It needs durable artifacts and better semantic layers, not a dashboard.

### Control plane

Authentication, shared quotas, provider routing, multi-tenant budgets and public rate limiting are intentionally assigned to a future gateway. That boundary is sensible. The Compose service must therefore not be presented as safe for direct public exposure.

## 6. Architecture review by module

### `api/main.py`

**Strengths**

- Clear orchestration; business logic remains in collaborators.
- Errors from schema, content, provider, budget and idempotency are consistently mapped.
- Cost is reconciled even when the provider pipeline fails validation.
- Successful responses only are stored for replay.

**Issues and implications**

1. The 422 terminal validation body omits known billed cost. This is the remaining #57 blocker.
2. `field_confidence` is presence, not confidence. Rename/add `field_presence` before consumers depend on it.
3. The response `data` is `dict[str, Any]`, so generated OpenAPI cannot describe doc-specific output precisely.
4. No request ID, run ID, build SHA, prompt version, schema hash, token counts or cost source is exposed/captured.
5. A process-local budget is not a quota. Restarts and multiple workers create independent counters.
6. Only successful responses are idempotently stored. Retrying a paid terminal 422 under the same key can spend again.
7. Concurrent same-key calls can race and duplicate spend; acceptable only while single-process is a declared boundary.

**Recommendation**

Do not redesign the endpoint. Add benchmark provenance primarily to the run journal, add safe request/run IDs, surface failed cost, and deprecate the misleading confidence name. Leave multitenant/quota behavior to the gateway.

### `api/content.py`

**Strengths**

- Decoded PDF size, page count and extracted text size are bounded.
- OCR is explicitly excluded.
- Malformed PDFs fail before provider spend.

**Risks**

- PyMuPDF still parses untrusted binary content inside the API process.
- Page/text bounds do not fully bound parser CPU.
- Base64 bodies are loaded before decode; a reverse proxy should enforce body size.
- Extracted text has no page delimiters or layout/provenance spans.

**Recommendation**

For controlled internal/gateway traffic, keep the current design. Before public PDF traffic, add container CPU/memory/PID limits, read-only root filesystem, dropped capabilities, a request deadline, and consider isolating PDF extraction into a preprocessor process. Do not add OCR inside the core service.

### `api/idempotency.py`

**Strengths**

- SQLite WAL and busy timeout are appropriate for one-host v1.
- First-writer-wins storage is simple.
- Payload hash conflicts and expiry semantics are explicit.

**Gaps**

- Check-then-call-then-put is not atomic.
- There is no pending reservation/lease/recovery state.
- Stale rows are lazily ignored, but automatic sweeping/size bounds are not evident in the endpoint path.
- The store interface can carry status codes, while runtime currently stores only successful typed responses.

**Recommendation**

Keep sequential semantics until there is a real multi-worker trigger. Add a deployment assertion/runbook: one worker only unless #42 is resolved. Consider a bounded on-write sweep. Design pending reservations only with explicit in-flight HTTP semantics.

### `api/budget.py`

The budget guard is useful as a **benchmark fuse**, not a production billing control. It uses a process-local floating-point total and check-then-reconcile behavior, so concurrent calls can overshoot and restarts reset the cap. Rename/document its scope accordingly. Shared budgets and actual billed cost belong at the gateway.

Use integer micro-dollars or `Decimal` if exact accounting becomes a product contract. Add a cost-source field because missing provider usage currently risks looking like genuine zero cost.

### `llm/client.py`

**Strengths**

- Provider selection is isolated.
- Direct-provider and gateway credentials are explicit.
- Prices are not given a universal silent default.
- Timeout/retry settings are bounded in concept.
- Lazy imports keep provider dependencies separated.

**Hardening**

- Fail if a real provider model ID is empty.
- Reject negative, zero, non-finite timeout values and negative retries.
- For a paid benchmark, refuse unknown/missing usage or mark cost as unknown rather than silently zero.
- Record requested provider, effective provider, effective model, SDK version and provider request identifier/hash in the journal.
- Keep a live canary after provider SDK upgrades; mocked CI cannot prove remote request compatibility.

### `llm/pipeline.py`

The two-attempt loop is appropriately simple. Improvements should preserve that simplicity:

- delimit untrusted document content and retry diagnostics explicitly;
- version and hash the prompt;
- add doc-type instruction blocks matching label policy;
- cap retry prompt growth or store a validation summary rather than unrestricted previous output;
- expose per-attempt token/cost/latency data to the evidence journal;
- keep provider transport retries separate from semantic validation retry.

The generic prompt currently says never infer, while total-only invoice v1 labels require a convention. The fix is not hidden prompt cleverness: disclose the convention for v1 and design a faithful v2 later.

### Schemas

**Invoice v1** is strict and useful but narrow. It cannot faithfully express total-level shipping/discount/rounding, and `subtotal_minor` cannot be null. `tax_minor:null` disables total reconciliation. Negative values and non-finite fractional quantities need an explicit credit-note/value-domain decision.

**Job posting v1** should reject negative salaries and blank values before the first baseline. The model also compresses nuanced visa wording into offered/not_offered/unspecified and does not represent salary basis such as pro-rata/OTE. These are acceptable v1 limits if fixtures are reviewed and caveated.

Do not add many new job fields before baseline. First learn whether the current fields are extracted reliably.

### `harness/scoring.py`

This is the highest-value refactor.

Current problems:

- hallucination divided by all fields understates the relevant failure;
- failed extraction marks expected-null values as missed;
- request reliability, schema acceptance and semantic correctness are blended;
- line items are one opaque top-level field;
- success-only cost/latency can look better as failures rise;
- p95 on a tiny sample is unstable without sample-size context;
- no document-level exact match or confidence interval is prominent.

Recommended metric layers:

1. **Request layer**
   - attempted fixtures;
   - infrastructure success/reachability;
   - control-plane skips;
   - transport/provider failure frequencies.
2. **Extraction layer**
   - accepted extraction rate;
   - first-pass schema-valid rate;
   - retry recovery rate;
   - terminal validation failure rate.
3. **Semantic layer, only for schema-valid predictions**
   - value exact accuracy over expected-non-null opportunities;
   - null correctness over expected-null opportunities;
   - hallucination opportunity rate over expected-null opportunities;
   - per-field and path-level counts;
   - whole-document exact match.
4. **Strict end-to-end layer**
   - fully correct documents / all eligible fixtures.
5. **Economics and latency**
   - total attempted spend;
   - failed spend;
   - cost per attempted, accepted and fully-correct document;
   - p50/p95 for all terminal requests and successful requests separately;
   - token counts and retry distribution.

This avoids both gaming and semantic corruption.

### `harness/run_accuracy.py`

The runner already preflights fixtures and protects final report output, but it should become a small evidence transaction engine:

- create a frozen manifest before first call;
- append one JSONL event/result per fixture and flush it;
- derive final report from the journal;
- support resume only when manifest/corpus/config hashes match;
- enforce one effective provider/model per section;
- make infrastructure abort thresholds explicit;
- persist error code, attempts, tokens, cost, latency and response hash;
- omit raw documents/raw model output by default;
- use run-specific idempotency keys only when retry semantics are clearly defined;
- mark partial/incomplete runs as ineligible for README promotion.

### CI and repository governance

The current CI quality is strong. The branch is protected, but the observed required checks are `lint + types + tests` and `secret scan (gitleaks)`; the Docker image build is not listed as required branch protection. Make the Docker gate required or aggregate all release checks into one required job.

The workflow comments state a preference for immutable action SHAs, but not every action reference is immutable. Normalise that policy during operational hardening.

The shared deny floor is current and T2 is declared, but the committed Claude settings no longer visibly wire local `PreToolUse`. Prove whether a global adapter intentionally supplies it. Add fast digest evidence and run the large canonical matrix only on relevant path changes, scheduled or manually; running thousands of cases on every ordinary code PR is unnecessary.

## 7. Issue-state verdict

The open issue count overstates remaining product work because tracking was not closed as fixes landed.

### Close now as fixed/obsolete

- #86: T2 tier declaration exists.
- #87: tier exists and project-scope bypass permissions were removed.
- #91: vendored floor is already 1.6.20.

### Rewrite or split

- #74: most loss-protection work landed; move transport policy and failed-cost remainder, then close.
- #79: split fixture generation from offline rehearsal.
- #80: split schema decision from dead-code/label tooling; validator crash is done.
- #88: rewrite for current global/local wiring and provenance question.
- #57: retitle around failed-validation cost only.

### Release blockers

- #46 metric semantics;
- #57 failed spend;
- T15 corpus completion;
- T17 paid pilot/full benchmark and report.

### Post-evidence/future

- #32 auth-era HTTP taxonomy footgun;
- #42 concurrent idempotency;
- #35/#54 invoice.v2;
- #10 periodic currency maintenance;
- #83 legacy hook cleanup;
- #13 should move to the shared agent-harness if still relevant.

See `review/03-issue-triage.md` and `machine/issue-triage.json` for exact actions.

## 8. Human versus agent work

The project is not simply “blocked on Chris.” Agents can remove most blank-page work, but humans must remain accountable for a small number of truth/spend decisions.

### Agent can do now

- merge/refresh #119 and rerun gates;
- close stale issues and seed coherent milestones/labels;
- reconcile docs against code;
- implement metric layers, failed cost, journal/resume and manifests;
- generate synthetic DRAFT fixtures and coverage matrices;
- build offline perfect/failure rehearsals;
- generate reports from journals;
- create release-gate comparator and canary strata;
- harden deployment/runbooks after evidence.

### Human must do

- approve what metrics mean;
- approve transport retry/cost semantics;
- review and promote fixture labels;
- source/anonymize/license-check real documents;
- configure private keys, current model IDs and prices;
- authorise paid calls and maximum spend;
- prevent label overfitting after seeing failures;
- approve public claims and release;
- verify global agent hook wiring;
- decide long-term licence and invoice.v2 scope.

The bundle’s task graph encodes these as hard dependencies rather than vague “owner action” notes.

## 9. Critical path

```text
W0 current-state preflight + dependency PR
       |
W1 backlog/docs reconciliation
       |
W2 metric contract + failed cost + transport policy + journal/manifest
       |                                |                          W3 synthetic drafts + human real/reviewed corpus
       |                         /
W4 full offline perfect/failure/interruption rehearsal
       |
W5 explicit paid pilot -> human review -> frozen full run
       |
W6 generated report -> human claim approval -> v0.1 release -> baseline promotion
       |
W7 release-gate cadence + operational and agent-harness hardening
```

The implementation work in W2-W4 is likely only several focused engineering days. Calendar time is dominated by human corpus review and real-fixture sourcing. For a solo developer who protects a few focused sessions, a credible measured release is realistically a **one-to-two-week** effort; it can take longer if real fixture provenance is hard to obtain. An invoice-only development preview could be earlier, but must be labelled narrowly.

## 10. Product horizon

### Horizon 0: finish the evidence promise

Deliver a complete, reproducible report before expanding scope. The first release should prove:

- strict extraction actually succeeds at an acceptable rate;
- absent fields are not systematically invented;
- validation retry recovers useful cases;
- failures and spend are honestly counted;
- the same corpus can compare providers/models;
- results can be reproduced from a run manifest and journal.

### Horizon 1: turn it into a release-gate workload

Once a baseline exists, package:

- a corpus manifest;
- a run contract;
- a comparator;
- relative regression thresholds;
- a cheap representative canary subset;
- human-approved baseline promotion.

This lets the project test model upgrades, prompt changes, schema changes, SDK changes and gateway routing. That is a stronger reusable asset than a static README table.

### Horizon 2: use it as an internal service

Behind a gateway, it can serve internal applications that need strict invoice/job extraction. Add request IDs, structured logs and gateway metadata; keep auth/quota/routing out of the core service. This is a good component for your broader internal tool ecosystem and DeliveraSoft work.

### Horizon 3: verticalise only with evidence of demand

Potential product paths include:

- invoice ingestion and review for a specific SME workflow;
- job-posting intelligence for recruitment/market analysis;
- “schema extraction as a governed service” for consultancy clients;
- a benchmark/release-gate product for teams changing models or gateways.

A standalone generic extraction API is the least differentiated of these. A vertical workflow gains value from proprietary labels, corrections, review queues and downstream integrations, not just the endpoint.

### Horizon 4: invoice.v2 and richer evidence

Only after v1 failures show the need:

- nullable subtotal;
- shipping, discounts, fees and rounding;
- credit notes and negative amounts;
- multiple tax rates;
- per-field source spans/page provenance;
- calibrated confidence from observed error data;
- human review routing;
- cheap-first/model-escalation cascades;
- active learning from corrected outputs.

OCR and async batch should be adapters around the core, activated by real workload requirements.

## 11. Expansion ideas worth preserving

### Evidence and experimentation

- Metamorphic fixtures: harmless whitespace/order/date-format transformations with invariant expected output.
- Prompt/model A/B runs with frozen corpus and paired significance reporting.
- Error clusters by validation type and field path.
- “Cost per fully correct document” as the practical optimisation target.
- Paired provider disagreement review queue.
- Baseline drift dashboard generated from run artifacts, not a database-first UI.

### Runtime

- Doc-specific prompt policy blocks generated from schema/label guide.
- Model cascade: low-cost model first, escalate only on validation or high-risk field patterns.
- Content fingerprinting to avoid repeated extraction across clients at gateway scope.
- Response provenance with page/text spans.
- Optional webhook/batch adapter outside the synchronous core.

### Corpus

- Private holdout set to reduce prompt overfitting.
- Adversarial mutation generator for numbers, dates, missing fields and conflicting totals.
- Duplicate/near-duplicate detection.
- Reviewer disagreement tracking.
- A “fixture admissibility” linter that rejects cases the schema cannot faithfully represent.

## 12. Explicit no-go list before v0.1 evidence

Do not spend the critical path on:

- OCR;
- async job queues;
- more providers;
- a UI/dashboard;
- auth/multitenancy inside the service;
- distributed idempotency;
- invoice.v2 implementation;
- arbitrary user-uploaded schemas;
- LLM judges;
- calibrated confidence;
- public internet exposure;
- full paid evaluation on every PR.

Each is potentially valid later. None solves the current credibility bottleneck.

## 13. Definition of accelerated success

The bundle has succeeded when the repository has:

1. a clean and accurate backlog;
2. an approved metric/transport contract;
3. an append-only evidence journal and frozen run manifest;
4. a reviewed, stratified corpus for both document types or an explicitly narrower claim;
5. a green full offline rehearsal including failure/resume cases;
6. a small paid canary followed by a complete frozen run;
7. a generated public report with honest denominators, cost and latency;
8. a formal v0.1 release artifact;
9. a promoted release-gate baseline;
10. no paid call or ground-truth promotion performed without human approval.
