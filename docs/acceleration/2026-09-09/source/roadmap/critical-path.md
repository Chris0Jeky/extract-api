# Critical path and execution waves

Snapshot: `aeacafa63685af3b47030375d13b2b5c1d5979f9`

## W0: Current-state proof

### A00  -  Revalidate snapshot against current main
- **Owner:** agent
- **Priority:** P0
- **Depends on:** none
- **Paid:** no
- **Acceptance:**
  - Record current HEAD and diff from aeacafa
  - Stop and rebase the plan if benchmark contracts changed
- **Proof:**
  - git status --short
  - git log -1 --oneline

### A01  -  Merge or refresh dependency PR #119
- **Owner:** agent
- **Priority:** P1
- **Depends on:** A00
- **Paid:** no
- **Acceptance:**
  - PR merged or a reasoned hold is recorded
  - Exact-head CI remains green
- **Proof:**
  - make ci-quick
  - make smoke
  - Docker CI

### A02  -  Capture baseline proving checks
- **Owner:** agent
- **Priority:** P0
- **Depends on:** A01
- **Paid:** no
- **Acceptance:**
  - Record test count, coverage, lint, mypy, fixture validation and smoke results from the actual checkout
  - Do not copy stale numbers from CLAUDE.md
- **Proof:**
  - make ci-quick
  - make fixtures-validate
  - make smoke

## W1: Backlog and authority hygiene

### A10  -  Close stale issues #86, #87 and #91
- **Owner:** agent
- **Priority:** P1
- **Depends on:** A00
- **Paid:** no
- **Acceptance:**
  - Each issue has a concise evidence comment and is closed
  - No code change is bundled

### A11  -  Rewrite/split omnibus issues #74, #79, #80 and #88
- **Owner:** agent
- **Priority:** P1
- **Depends on:** A00
- **Paid:** no
- **Acceptance:**
  - Historical completed items are closed or checked off
  - Each remaining issue has one coherent contract and owner

### A12  -  Create evidence-focused milestones and labels
- **Owner:** agent
- **Priority:** P1
- **Depends on:** A11
- **Paid:** no
- **Acceptance:**
  - M5 Evidence-ready benchmark, M6 Measured v0.1, M7 Release-gate workload exist
  - Human-required and paid-call work is visibly labelled

### A13  -  Reconcile documentation drift
- **Owner:** agent
- **Priority:** P1
- **Depends on:** A02
- **Paid:** no
- **Acceptance:**
  - API shapes match current code
  - Coverage/test numbers are measured or explicitly labelled as claims
  - Provider and fixture status match main
  - One canonical state source is introduced or proposed
- **Proof:**
  - make ci-quick

## W2: Benchmark contract and durability

### H20  -  Approve benchmark metric contract
- **Owner:** human
- **Priority:** P0
- **Depends on:** A13
- **Paid:** no
- **Acceptance:**
  - Choices for failure layers, null denominator, nested scoring and headline metrics are explicit

### A20  -  Implement layered scoring and null-opportunity metrics
- **Owner:** agent
- **Priority:** P0
- **Depends on:** H20
- **Paid:** no
- **Acceptance:**
  - Infrastructure, extraction and semantic outcomes are separate
  - Hallucination opportunity rate uses expected-null denominator
  - Failed extraction does not claim absent values were missed
  - Document exact match and accepted-extraction rate are reported
- **Proof:**
  - focused scoring tests
  - make ci-quick

### A21  -  Add path-level nested line-item diagnostics
- **Owner:** agent
- **Priority:** P1
- **Depends on:** A20
- **Paid:** no
- **Acceptance:**
  - Whole-list exactness remains
  - Index-aligned field paths are reported without fuzzy matching
  - Order-sensitive contract is documented
- **Proof:**
  - nested match/mismatch/reorder cases

### A22  -  Surface and aggregate failed-validation spend
- **Owner:** agent
- **Priority:** P0
- **Depends on:** H20
- **Paid:** no
- **Acceptance:**
  - Terminal 422 includes finite nonnegative cost_usd
  - Harness includes successful and failed spend
  - Report distinguishes attempted, accepted and failed cost
- **Proof:**
  - 422 two-attempt cost
  - zero-cost pre-request 422
  - malformed error body

### H23  -  Approve transport failure and retry policy
- **Owner:** human
- **Priority:** P0
- **Depends on:** H20
- **Paid:** no
- **Acceptance:**
  - Unsent, ambiguous-sent, provider and control-plane outcomes are defined
  - Retry count and abort threshold are defined

### A23  -  Implement transport classification
- **Owner:** agent
- **Priority:** P0
- **Depends on:** H23
- **Paid:** no
- **Acceptance:**
  - Provably unsent errors receive bounded retry
  - Ambiguous sent errors are journalled and not silently retried
  - Infrastructure failures do not enter semantic denominators
  - Run abort threshold prevents publishing a degraded partial run as complete
- **Proof:**
  - connect error
  - TLS/DNS error
  - read timeout
  - HTTP 502/504
  - control-plane 402/409

### A24  -  Add durable run manifest, JSONL journal and resume
- **Owner:** agent
- **Priority:** P0
- **Depends on:** A20, A22, A23
- **Paid:** no
- **Acceptance:**
  - Each fixture result is persisted before next call
  - Journal is append-only and flushed
  - Resume refuses changed corpus/config hashes
  - Final summary is derived from journal, not transient memory
- **Proof:**
  - kill/resume simulation
  - corrupt journal line
  - manifest mismatch
  - duplicate fixture entry

### A25  -  Freeze and verify run provenance
- **Owner:** agent
- **Priority:** P0
- **Depends on:** A24
- **Paid:** no
- **Acceptance:**
  - Manifest captures repo/build/provider/model/SDK/prompt/schema/corpus/pricing hashes
  - Run fails on provider/model drift
  - Response exposes or journal captures token and attempt metadata
  - Secrets and raw document content are excluded by default
- **Proof:**
  - mixed provider response
  - model changes mid-run
  - redaction snapshot

### H26  -  Approve targeted job-schema tightening
- **Owner:** human
- **Priority:** P1
- **Depends on:** A13
- **Paid:** no
- **Acceptance:**
  - Decision on negative salaries and blank strings is recorded

### A26  -  Apply targeted job-schema invariants
- **Owner:** agent
- **Priority:** P1
- **Depends on:** H26
- **Paid:** no
- **Acceptance:**
  - Negative salary values fail
  - Blank title/company/location values fail when non-null
  - No whitespace/value coercion is introduced
- **Proof:**
  - schema adversarial cases
  - provider schema generation

## W3: Corpus factory and human review

### A30  -  Import synthetic DRAFT fixture candidates
- **Owner:** agent
- **Priority:** P0
- **Depends on:** A26
- **Paid:** no
- **Acceptance:**
  - No existing fixture is overwritten
  - All imported files remain DRAFT
  - Fixture validator passes
- **Proof:**
  - make fixtures-validate

### A31  -  Generate corpus inventory, hashes and coverage matrix
- **Owner:** agent
- **Priority:** P0
- **Depends on:** A30
- **Paid:** no
- **Acceptance:**
  - Every fixture has source/status/edge-case tags in a sidecar manifest
  - Reviewed and DRAFT counts are generated
  - Corpus hash is deterministic
- **Proof:**
  - manifest determinism
  - unknown fixture detection

### H30  -  Review synthetic invoice labels
- **Owner:** human
- **Priority:** P0
- **Depends on:** A31
- **Paid:** no
- **Acceptance:**
  - Each accepted fixture is independently checked against content
  - Ambiguous cases remain DRAFT or are corrected
  - REVIEWED flips are human-authored commits
- **Proof:**
  - make fixtures-validate

### H31  -  Review synthetic job-posting labels
- **Owner:** human
- **Priority:** P0
- **Depends on:** A31
- **Paid:** no
- **Acceptance:**
  - Salary, period, seniority, remote and visa semantics are checked
  - Ambiguous right-to-work wording is not overclaimed
- **Proof:**
  - make fixtures-validate

### H32  -  Source and anonymize real invoice fixtures
- **Owner:** human
- **Priority:** P0
- **Depends on:** A31
- **Paid:** no
- **Acceptance:**
  - Target reviewed corpus size/strata are met
  - No personal/company identifiers remain
  - Rights/provenance review is recorded
- **Proof:**
  - manual privacy review
  - make fixtures-validate

### H33  -  Source and anonymize real UK job-posting fixtures
- **Owner:** human
- **Priority:** P0
- **Depends on:** A31
- **Paid:** no
- **Acceptance:**
  - Roughly half of reviewed job fixtures are real-anonymized unless explicitly waived
  - Edge-case coverage is balanced
  - Source snapshots and rights notes are retained privately or as hashes
- **Proof:**
  - manual privacy review
  - make fixtures-validate

## W4: Offline end-to-end rehearsal

### A40  -  Build test-only fixture response map and in-process ASGI rehearsal
- **Owner:** agent
- **Priority:** P0
- **Depends on:** A24, A30
- **Paid:** no
- **Acceptance:**
  - Production client cannot access expected labels
  - Perfect corpus run traverses real endpoint/pipeline/scorer/report path
  - Fixture mapping is keyed by content hash or fixture ID supplied only by harness
- **Proof:**
  - perfect run
  - unknown hash
  - production import guard

### A41  -  Rehearse error and interruption matrix offline
- **Owner:** agent
- **Priority:** P0
- **Depends on:** A40
- **Paid:** no
- **Acceptance:**
  - 422 cost, provider error, timeout, connect failure, budget skip, mixed provider, crash/resume and output failure are exercised
- **Proof:**
  - full rehearsal suite

### A42  -  Create benchmark report snapshots and claim guard
- **Owner:** agent
- **Priority:** P1
- **Depends on:** A41
- **Paid:** no
- **Acceptance:**
  - Report labels denominators and incomplete runs
  - README cannot replace Numbers pending without a complete approved run manifest
- **Proof:**
  - snapshot tests
  - incomplete run claim guard

## W5: Paid pilot and full benchmark

### H50  -  Configure and verify paid provider settings
- **Owner:** human
- **Priority:** P0
- **Depends on:** A42, H30, H31, H32, H33
- **Paid:** yes
- **Acceptance:**
  - Model IDs are current and intentional
  - Input/output prices and source date are recorded
  - Budget is approved
  - Keys never enter git or logs
- **Proof:**
  - configuration preflight only

### A50  -  Estimate run cost before calls
- **Owner:** agent
- **Priority:** P0
- **Depends on:** H50
- **Paid:** no
- **Acceptance:**
  - Upper-bound estimate uses corpus byte/token estimate, max output and retry policy
  - Run refuses zero/unknown prices unless explicitly acknowledged
- **Proof:**
  - price validation
  - budget too small

### H51  -  Authorize paid pilot
- **Owner:** human
- **Priority:** P0
- **Depends on:** A50
- **Paid:** yes
- **Acceptance:**
  - Explicit run ID, providers, models, fixtures and maximum spend are approved

### A51  -  Run small paid canary
- **Owner:** agent
- **Priority:** P0
- **Depends on:** H51
- **Paid:** yes
- **Acceptance:**
  - 2-3 representative fixtures per provider/domain complete
  - Provider SDK live compatibility is proven
  - Manifest, journal, summary and report are preserved
- **Proof:**
  - manual result inspection

### H52  -  Approve full paid run after pilot
- **Owner:** human
- **Priority:** P0
- **Depends on:** A51
- **Paid:** yes
- **Acceptance:**
  - Pilot anomalies are resolved or accepted
  - Full budget and corpus version are frozen

### A52  -  Run full frozen benchmark
- **Owner:** agent
- **Priority:** P0
- **Depends on:** H52
- **Paid:** yes
- **Acceptance:**
  - Every eligible fixture has a terminal journal state
  - No provider/model/corpus drift occurred
  - Incomplete infrastructure conditions prevent report promotion
- **Proof:**
  - manifest validator
  - journal completeness

### H53  -  Review outliers and label disputes
- **Owner:** human
- **Priority:** P0
- **Depends on:** A52
- **Paid:** no
- **Acceptance:**
  - Label errors are corrected in a new corpus version, never silently in-place under the same report
  - Model failures are not relabelled away without rationale
- **Proof:**
  - second-review on changed labels

## W6: Publish and promote baseline

### A60  -  Generate final measured report and README tables
- **Owner:** agent
- **Priority:** P0
- **Depends on:** H53
- **Paid:** no
- **Acceptance:**
  - Report includes corpus/provider/model/provenance, denominators, confidence intervals/caveats, cost and latency
  - Numbers are generated from journal
  - No unmeasured capability language replaces evidence
- **Proof:**
  - report regeneration is deterministic

### H60  -  Approve public claims and release boundary
- **Owner:** human
- **Priority:** P0
- **Depends on:** A60
- **Paid:** no
- **Acceptance:**
  - Claims match measured domains and corpus
  - Known schema limitations are disclosed
  - License posture is accepted

### A61  -  Publish v0.1.0 release artifact
- **Owner:** agent
- **Priority:** P1
- **Depends on:** H60
- **Paid:** no
- **Acceptance:**
  - A signed/verified tag or release is created
  - Report and manifest are attached or linked
  - No secrets/raw private fixtures are shipped
- **Proof:**
  - release build
  - Docker smoke

### A62  -  Create release-gate baseline and comparator
- **Owner:** agent
- **Priority:** P1
- **Depends on:** A61
- **Paid:** no
- **Acceptance:**
  - Baseline promotion is explicit
  - Relative quality/cost/latency regressions fail with useful diagnostics
  - No absolute threshold is invented before data
- **Proof:**
  - pass/equal
  - quality regression
  - cost regression
  - latency regression

### H62  -  Approve baseline promotion and paid cadence
- **Owner:** human
- **Priority:** P1
- **Depends on:** A62
- **Paid:** no
- **Acceptance:**
  - Baseline SHA/run ID and cadence budget are explicit

## W7: Post-evidence hardening

### A70  -  Prove agent-harness wiring and pin floor provenance
- **Owner:** agent+independent review
- **Priority:** P1
- **Depends on:** A60
- **Paid:** no
- **Acceptance:**
  - Actual PreToolUse route is documented
  - Digest check is fast and required
  - Full matrix is path-filtered/scheduled
  - No autonomous weakening of guard semantics occurs
- **Proof:**
  - canonical smoke matrix
  - digest mismatch

### A71  -  Retire duplicate hook and normalization dead code
- **Owner:** agent
- **Priority:** P2
- **Depends on:** A70
- **Paid:** no
- **Acceptance:**
  - Each module is either wired to a named product workflow or removed
  - Coverage remains meaningful rather than preserved for dead code
- **Proof:**
  - make ci-quick
  - make test-hooks

### A72  -  Harden gateway-only deployment and observability
- **Owner:** agent
- **Priority:** P1
- **Depends on:** A61
- **Paid:** no
- **Acceptance:**
  - No direct public exposure in documented deployment
  - Request/run IDs and structured redacted logs exist
  - Container has resource/security options appropriate to untrusted PDFs
  - Docker build is a required gate
- **Proof:**
  - deployment smoke
  - log redaction
  - resource-limit test

### A73  -  Create trigger-gated future epics
- **Owner:** agent
- **Priority:** P3
- **Depends on:** A61
- **Paid:** no
- **Acceptance:**
  - Invoice.v2, concurrent idempotency, auth taxonomy and ISO maintenance have explicit activation triggers
