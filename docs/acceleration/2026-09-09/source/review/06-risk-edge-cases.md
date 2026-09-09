# Risk and edge-case register

| ID | Severity | Area | Risk | Mitigation | Trigger |
|---|---|---|---|---|---|
| R01 | **critical** | Evidence | Publishing two-domain accuracy with no reviewed job-posting corpus | Block headline claims until corpus minimum and review gates pass. | Any README/report update with two-domain numbers |
| R02 | **high** | Metrics | Hallucination rate diluted by all-fields denominator | Use expected-null opportunities and null-correct counts. | Before first paid full run |
| R03 | **high** | Metrics | Failed extractions corrupt null-field semantics | Layer extraction outcome and semantic scoring; add strict document success. | ADR-0005 |
| R04 | **high** | Cost | Terminal 422 spend omitted from totals | Surface billed cost in error payload and journal every attempt. | #57 |
| R05 | **high** | Durability | Interrupted paid run loses in-memory evidence | Append-only journal with fsync and hash-validated resume. | Before full paid run |
| R06 | **high** | Provenance | Mixed model/provider/config in one report | Frozen manifest and per-result consistency checks. | Run start and each response |
| R07 | **high** | Operations | Unauthenticated public exposure causes paid-call abuse | Gateway-only binding, TLS, auth, rate limits and upstream budget. | Any external deployment |
| R08 | **medium** | PDF | Untrusted PDF consumes CPU/memory or exploits parser surface | Gateway size limit, container limits, read-only filesystem, timeout and isolated preprocessor if public. | External PDF traffic |
| R09 | **medium** | Runtime | Per-process budget resets/repeats across workers | Treat as benchmark safety only; gateway/shared store owns production quota. | More than one process or restart-sensitive budget |
| R10 | **medium** | Idempotency | Concurrent same-key calls duplicate spend | Keep single-process boundary; add atomic reservation before scaling. | Multiple workers/replicas |
| R11 | **medium** | Schema | v1 total-only convention contradicts never-infer prompt | Disclose convention, avoid new total-only fixtures, design invoice.v2 after baseline. | Corpus review |
| R12 | **medium** | Docs | Agents act on stale STATUS/PLAN/ADR claims | Canonical state file and drift checks. | Every status-changing PR |
| R13 | **medium** | Agent harness | Vendored floor provenance/wiring is unproven | Audit global adapter, pin digests, gated canonical matrix. | #88 rewrite |
| R14 | **medium** | Supply chain | Not every CI action is immutable-SHA pinned and Docker check is not a required branch check | Pin third-party actions and require the Docker job or aggregate required gate. | CI hardening wave |
| R15 | **low** | API | Presence heuristic is mistaken for calibrated confidence | Rename to field_presence or remove before formal consumers. | v0.1 contract freeze |

## Additional edge cases to test

- provider returns schema-valid JSON with the wrong effective model;
- provider usage is missing, partial or non-finite;
- terminal 422 is billed but response body is malformed;
- document is valid PDF but extracts only whitespace;
- repeated headers/footers dominate extracted text;
- base64 body reaches reverse-proxy limit before decoded PDF limit;
- process dies after provider response but before journal append;
- process dies after journal append but before summary write;
- resume sees duplicate or truncated last JSONL record;
- corpus label changes after a run but retains the same version;
- two fixtures share an ID or content hash;
- provider default changes between fixtures;
- price configuration changes mid-run;
- budget is reached between semantic retry attempts;
- idempotency replay returns old model output after default model changes;
- concurrent same-key requests with same and different payloads;
- invoice tax is null and total arithmetic is inconsistent;
- line items reorder while values remain identical;
- job posting has pro-rata, OTE, day-rate or conditional sponsorship wording;
- relative posted date without a document reference date;
- zero/negative/NaN amounts or quantities;
- Unicode look-alikes in currency or identifiers;
- prompt injection text asks the model to ignore the schema;
- report is generated from an incomplete run and accidentally promoted.