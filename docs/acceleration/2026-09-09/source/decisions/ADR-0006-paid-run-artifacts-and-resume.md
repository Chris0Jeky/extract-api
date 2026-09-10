# ADR-0006: Durable paid-run artifacts and hash-safe resume

- Status: Proposed
- Related: T17, #74

## Context

A paid benchmark currently aggregates results in memory and writes a final Markdown report. Preflight and output preservation reduce several loss modes, but a process crash, terminal interruption or host failure can still discard already billed per-fixture evidence. A final Markdown file also lacks enough machine provenance for reliable comparison.

## Decision

Every run uses a directory:

```text
evals/runs/<run_id>/
  manifest.json
  journal.jsonl
  summary.json
  report.md
  approval.json          # optional/human-created
  logs/                  # redacted diagnostics only
```

### Manifest

`manifest.json` is created and validated before the first provider call. It freezes:

- repository SHA and dirty state;
- application/Python/dependency/container identity;
- corpus version, fixture list and hash;
- provider/model/SDK identities;
- prompt version/hash;
- schema hashes;
- prices, price date and cost source;
- timeout/retry/max-attempt policy;
- budget and paid approval reference.

Mutable run state is limited to `state`, timestamps and completion metadata. Identity fields may not change during resume.

### Journal

`journal.jsonl` is append-only. One terminal record is flushed and `fsync`ed after each fixture before the next call. Records include:

- sequence number;
- run/fixture IDs and fixture hash;
- provider/model identity;
- request/extraction outcome;
- HTTP/error classification;
- attempts, token counts, cost and latency;
- predicted canonical data or a redacted/hash reference according to repository policy;
- semantic scoring payload or enough information to recompute it;
- timestamps and response hash.

Do not persist raw source content or raw model output by default.

### Resume

Resume must:

1. parse every complete journal line;
2. reject duplicate terminal fixture records unless explicitly marked superseded;
3. reject changed manifest identity, corpus hash, fixture hash, provider/model/prompt/schema/pricing or policy;
4. continue only missing fixtures in the original deterministic order;
5. preserve sequence numbers;
6. regenerate summary/report from the entire journal.

A truncated final line may be quarantined only if it is provably the last incomplete append; all earlier corruption invalidates the run.

### Atomic derived artifacts

Write `summary.json` and `report.md` to temporary sibling files, flush, then `os.replace`. They are disposable derivatives of manifest+journal.

### State machine

`planned -> running -> complete`

Exceptional terminal states:

- `aborted`: deliberate operator/infrastructure stop; potentially resumable;
- `invalid`: identity/journal corruption or contract violation; never promotable.

## Consequences

- A crash loses at most the currently in-flight call, not prior evidence.
- Paid runs become auditable and resumable.
- Comparison/gating can consume stable JSON rather than scrape Markdown.
- File management becomes part of the benchmark contract.

## Rejected alternatives

- Final report only: insufficient loss protection.
- Full database first: unnecessary operational/migration weight for a sequential evaluator.
- Reusing API idempotency storage as benchmark journal: mixes runtime replay and evidence concerns.

## Acceptance tests

- kill after N journal appends and resume N+1;
- fail before append after provider response and mark the fixture ambiguous on operator reconciliation;
- manifest/corpus/prompt/model mismatch refuses resume;
- duplicate fixture record invalidates run;
- truncated last JSONL line is handled only under explicit recovery mode;
- summary/report regenerate byte-for-byte from unchanged inputs;
- incomplete/aborted run cannot be promoted.
