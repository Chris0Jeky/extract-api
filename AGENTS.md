# AGENTS.md

Authoritative rulebook for anyone (human or agent) working in extract-api.
`CLAUDE.md` defers to this file. Precedence: an explicit instruction from Chris >
this file > inline code comments.

## Review and merge policy

One home for this policy: the twelve global laws in `~/.claude/CLAUDE.md` and the
tier table in agent-harness `BLUEPRINT.md` section 1 (operational detail: the
global `review-and-ship` skill). This repo's row: **T2 daily driver** per
`.agent-harness/tier.json` - push and merge free, self-review on green proving
checks, comments triaged once, no independent review round owed.

Repo-specific review lenses to carry into that pipeline: strict validation (never
silently coerce), the validation-retry loop (exact failure list, max 2 attempts,
422 trail), error-taxonomy correctness (exactly one code per non-200),
idempotency (replay / 409 / TTL), `cost_usd` emission, provider-seam isolation.

## Definition of Done

- Behavior changes ship with tests (unit/integration as appropriate). Handle
  error cases explicitly; never swallow failures (this is the same instinct as
  "fail loudly, never silently coerce").
- `make ci-quick` is green (ruff + mypy strict + pytest).
- Docs are updated when reality changes (README, PLAN, ADRs, this file).
- No secrets in any file; env refs only. No em dashes anywhere.
- Provider SDKs are imported only in `llm/client.py`.

## Work protocol

- Prefer incremental execution with small, file-scoped, conventional commits
  (`<area>: <imperative summary>`). More than ~3 changed files without a commit
  is a smell.
- One reviewable slice per PR. Do not mix code changes with strategy-doc changes.
- End every working session with a report: done / decisions needed / next
  unblocked tasks (see the handoff format in `.claude/skills/verify-and-sync`).

## Security baseline

- No secrets committed; ship `.env.example` only. `gitleaks` scans every PR.
- Safe git only: never bare `git push --force` (use `--force-with-lease`); no
  `rm -rf /`, no `git reset --hard` on shared work. See
  `docs/agentic/GIT_WORKFLOW.md`.
