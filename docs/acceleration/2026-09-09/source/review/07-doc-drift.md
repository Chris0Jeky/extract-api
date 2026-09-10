# Documentation and authority drift

## Observed drift

- `docs/STATUS.md` is a dated functional snapshot and does not reflect several later issue fixes.
- `CLAUDE.md` claims approximately 323 tests/99% coverage while the current configured floor is 95%; regenerate rather than manually preserve those counts.
- `docs/plan/PLAN.md` contains API/error shape wording that differs from the current `trail` response and optional idempotency behavior.
- ADR 0002 contains provider/job-schema/fallback descriptions that appear older than current implementation.
- Issue #57 retains four items although comments indicate only failed spend remains.
- Issue #74 retains an omnibus title although most sub-slices landed.
- Issues #86, #87 and #91 have false premises on current `main`.
- Issue #88 says local PreToolUse is wired, while committed settings no longer show that entry.
- `AGENTS.md` and comments are rich in rationale, but the same facts are repeated across several files.

## Recommendation: canonical project state

Add a small machine-readable file such as `docs/project-state.json` containing:

- current milestone and cut line;
- implemented capabilities;
- fixture counts by source/status/type;
- accepted ADR IDs;
- current schema/prompt versions;
- last complete benchmark run ID;
- release readiness gates;
- known deferred triggers.

Generate or check status tables from this file. Do not generate architectural rationale; ADRs remain the source for decisions. Add a CI drift check that verifies obvious facts such as configured coverage floor, registered schemas, fixture counts and floor version.

## Document roles

- `README.md`: external contract and measured evidence.
- `AGENTS.md`: concise repository operating rules.
- `CLAUDE.md`: adapter-specific guidance only; no duplicated volatile metrics.
- `docs/project-state.json`: current machine facts.
- `docs/STATUS.md`: generated human view of state.
- ADRs: durable accepted decisions.
- Issues/milestones: executable remaining work.
- `tasks/BACKLOG.md`: either generated from issues or retired after migration; do not maintain a second manual backlog indefinitely.
