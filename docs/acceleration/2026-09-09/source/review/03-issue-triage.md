# Open issue triage

Snapshot: `aeacafa63685af3b47030375d13b2b5c1d5979f9`

The table is intentionally operational: it separates historical issue narrative from current executable work.

| # | Current action | Priority | Owner | Recommendation |
|---:|---|---|---|---|
| [10](https://github.com/Chris0Jeky/extract-api/issues/10) | **KEEP / SCHEDULE** | P3 | agent, with human source approval | Convert to a scheduled six-month audit with a generated provenance file. Do not put it on the v0.1 critical path. |
| [13](https://github.com/Chris0Jeky/extract-api/issues/13) | **MOVE UPSTREAM / CLOSE** | P3 | human or independent top-model review | Revalidate against the canonical shared floor. Move any still-real gaps to agent-harness and close the repo-local legacy-hook issue. |
| [32](https://github.com/Chris0Jeky/extract-api/issues/32) | **KEEP / TRIGGER-GATED** | P3 | agent | Keep as a trigger-gated footgun. Resolve before adding authentication, authorization or new HTTPException-based middleware. |
| [35](https://github.com/Chris0Jeky/extract-api/issues/35) | **CONSOLIDATE INTO INVOICE.V2 EPIC** | P3 | human decision, agent design | Merge with #54 into one invoice.v2 design epic. Keep v1 frozen for the first evidence run and disclose the total-only convention. |
| [42](https://github.com/Chris0Jeky/extract-api/issues/42) | **KEEP / SCALE-TRIGGERED** | P3 | agent after human contract choice | Keep the sequential v1 contract. Implement pending reservations only before multi-worker or multi-replica deployment. |
| [46](https://github.com/Chris0Jeky/extract-api/issues/46) | **IMPLEMENT NOW** | P0 | agent after metric ADR approval | Replace the single outcome table with layered request/extraction/semantic accounting. Make expected-null opportunities the hallucination denominator. |
| [54](https://github.com/Chris0Jeky/extract-api/issues/54) | **CONSOLIDATE INTO INVOICE.V2 EPIC** | P3 | human decision, agent design | Combine with #35 and defer implementation until after a stable v1 baseline and real error evidence. |
| [57](https://github.com/Chris0Jeky/extract-api/issues/57) | **RETITLE / IMPLEMENT REMAINDER** | P0 | agent | Retitle around its only material remainder: expose billed cost on terminal validation failures and fold it into run totals. |
| [74](https://github.com/Chris0Jeky/extract-api/issues/74) | **SPLIT REMAINDERS / CLOSE** | P1 | agent | Move transport classification to ADR-0007/new issue, failed cost to #57, then close #74 with a completion summary. |
| [79](https://github.com/Chris0Jeky/extract-api/issues/79) | **SPLIT INTO TWO P0/P1 ISSUES** | P0 | agent drafts; human reviews | Generate synthetic DRAFT fixtures now. Implement rehearsal as a test-only content-hash response map or in-process ASGI runner, not a production expected-label echo mode. |
| [80](https://github.com/Chris0Jeky/extract-api/issues/80) | **SPLIT / CLOSE UMBRELLA** | P1 | agent with human schema approval | Close the fixed validator-crash item. Create one schema decision issue and one dead-code/label-tooling issue. |
| [83](https://github.com/Chris0Jeky/extract-api/issues/83) | **KEEP / DO AFTER #88** | P2 | agent, independently reviewed | Resolve current shared-floor wiring/provenance first, then retire legacy hook code and its coverage burden. |
| [86](https://github.com/Chris0Jeky/extract-api/issues/86) | **CLOSE AS FIXED** | P0 hygiene | agent | Close with evidence that .agent-harness/tier.json now declares T2. |
| [87](https://github.com/Chris0Jeky/extract-api/issues/87) | **CLOSE AS FIXED/OBSOLETE** | P0 hygiene | agent | Close: the tier declaration exists and the project-scope bypassPermissions setting was removed. |
| [88](https://github.com/Chris0Jeky/extract-api/issues/88) | **REWRITE** | P1 | human/independent top-model review | Rewrite around the current question: prove where PreToolUse is wired, pin canonical bytes, and run the large matrix only on floor/config changes or scheduled/manual workflows. |
| [91](https://github.com/Chris0Jeky/extract-api/issues/91) | **CLOSE AS FIXED** | P0 hygiene | agent | Close with current FLOOR_VERSION 1.6.20 evidence. |

## Detailed close/rewrite queue

### #10  -  Maintenance: periodic ISO-4217 refresh + currency-status audit

**Action:** KEEP / SCHEDULE  
**Priority:** P3  
**Owner:** agent, with human source approval

The current snapshot is recent enough for the pending benchmark, but currency membership is time-sensitive over the life of the service.

**Next actions**

- Add source/date/hash metadata
- Create audit script
- Open automated PR only when the set changes

### #13  -  Hook hardening backlog: obscure destructive-command bypass variants

**Action:** MOVE UPSTREAM / CLOSE  
**Priority:** P3  
**Owner:** human or independent top-model review

The issue targets the deprecated bespoke hook, while the repository now vendors a shared dispatcher. Keeping security-floor logic forked locally creates drift.

**Next actions**

- Do not let the constrained agent autonomously weaken its own guard
- Link upstream issue or close as obsolete

### #32  -  StarletteHTTPException degrade branch masks future non-404/405 client errors as 500

**Action:** KEEP / TRIGGER-GATED  
**Priority:** P3  
**Owner:** agent

It is currently unreachable but would invert future 4xx semantics into a 500.

**Next actions**

- Add a trigger label
- Resolve alongside the first new 4xx taxonomy code

### #35  -  Consider making subtotal_minor nullable for total-only invoices

**Action:** CONSOLIDATE INTO INVOICE.V2 EPIC  
**Priority:** P3  
**Owner:** human decision, agent design

The current schema forces a convention that conflicts with the never-infer story, but changing it now would invalidate the pending v1 baseline.

**Next actions**

- Create invoice.v2 epic
- Document current corpus convention
- Do not add more total-only fixtures to the reviewed v1 set

### #42  -  Idempotency: atomic reservation for concurrent same-key requests

**Action:** KEEP / SCALE-TRIGGERED  
**Priority:** P3  
**Owner:** agent after human contract choice

The current single-process use is coherent; solving distributed in-flight coordination before measured value is unnecessary complexity.

**Next actions**

- Add explicit deployment trigger
- Choose 202/425/409 semantics when activated

### #46  -  Accuracy: report hallucination rate over absent-field opportunities

**Action:** IMPLEMENT NOW  
**Priority:** P0  
**Owner:** agent after metric ADR approval

The current all-fields denominator can hide systematic hallucination and failed extractions currently corrupt null-field semantics.

**Next actions**

- Ratify ADR-0005 draft
- Add null-correct and no-prediction states
- Report document exact match and accepted-extraction rate separately

### #54  -  v1 invoice schema cannot represent total-level shipping/adjustment outside subtotal

**Action:** CONSOLIDATE INTO INVOICE.V2 EPIC  
**Priority:** P3  
**Owner:** human decision, agent design

This is a real representational limit, but the current milestone is evidence, not schema expansion.

**Next actions**

- Design explicit adjustment equation
- Decide credit-note semantics
- Version schema rather than mutate v1

### #57  -  T17 live-harness hardening

**Action:** RETITLE / IMPLEMENT REMAINDER  
**Priority:** P0  
**Owner:** agent

Malformed-2xx handling, configurable timeout and fixture placement have landed; leaving the omnibus title obscures what remains.

**Next actions**

- Add cost_usd to terminal 422 body
- Carry cost through PredictionFailed
- Report attempted, successful and failed spend separately

### #74  -  Harness paid-run loss-protection omnibus

**Action:** SPLIT REMAINDERS / CLOSE  
**Priority:** P1  
**Owner:** agent

Preflight, report preservation and deterministic failure logging already landed. A historical umbrella no longer reflects executable work.

**Next actions**

- Post completion comment
- Link successor issues
- Close

### #79  -  Synthetic DRAFT corpus + FixtureClient echo mode

**Action:** SPLIT INTO TWO P0/P1 ISSUES  
**Priority:** P0  
**Owner:** agent drafts; human reviews

Fixture authoring and harness rehearsal are independently valuable and have different risk profiles.

**Next actions**

- Import candidate fixtures from this bundle
- Create coverage matrix
- Build perfect/failure rehearsal maps outside production routing

### #80  -  Job salary/string hardening + normalize.py + validator crash

**Action:** SPLIT / CLOSE UMBRELLA  
**Priority:** P1  
**Owner:** agent with human schema approval

The current issue mixes a completed bug, a product-schema choice and an architecture cleanup.

**Next actions**

- Tighten job salary/nonblank semantics before baseline
- Either repurpose normalize.py as explicit label tooling or delete it

### #83  -  Retire legacy scripts/agent_hooks/pre_tool_use.py

**Action:** KEEP / DO AFTER #88  
**Priority:** P2  
**Owner:** agent, independently reviewed

The legacy module is not runtime code and keeps duplicate safety semantics alive.

**Next actions**

- Preserve only unique redaction tests
- Delete legacy module
- Update workflow docs

### #86  -  Main has no tier.json

**Action:** CLOSE AS FIXED  
**Priority:** P0 hygiene  
**Owner:** agent

The tracked T2 declaration exists on the reviewed main snapshot.

**Next actions**

- Post evidence
- Close

### #87  -  bypassPermissions + missing tier makes work-loss guards unprompted

**Action:** CLOSE AS FIXED/OBSOLETE  
**Priority:** P0 hygiene  
**Owner:** agent

Both premises of the issue are false on the reviewed head.

**Next actions**

- Reference tier file and commit 1266bbd
- Close

### #88  -  Vendored deny floor is live but unpinned and untested

**Action:** REWRITE  
**Priority:** P1  
**Owner:** human/independent top-model review

The committed settings no longer contain the local PreToolUse entry, so the July issue body is stale even though provenance/testing remains unresolved.

**Next actions**

- Audit global adapter
- Add fast digest check
- Add path-filtered or scheduled canonical matrix

### #91  -  Vendored floor is 1.5.2 against canonical 1.6.18

**Action:** CLOSE AS FIXED  
**Priority:** P0 hygiene  
**Owner:** agent

The reported version gap no longer exists on the reviewed main snapshot.

**Next actions**

- Post current version
- Close
