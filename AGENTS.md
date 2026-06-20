# AGENTS.md

Authoritative rulebook for anyone (human or agent) working in extract-api.
`CLAUDE.md` defers to this file. Precedence: an explicit instruction from Chris >
this file > inline code comments.

## Review Policy (non-negotiable)

1. **Post findings, then fix everything found.** Every finding at every severity
   (critical, high, medium, low) is addressed with a fix, a commit, and
   verification. There is no "non-blocking" category that gets silently ignored.
2. **Inspect all existing PR comments** (human and bots: Dependabot, CodeQL,
   gitleaks, prior review threads). Address anything unaddressed: fix it, reply
   with invalidation evidence, or seed a tracked follow-up issue. Tech debt from
   reviews must be zero.
3. **Two independent adversarial reviews per PR** before merge, run as distinct
   lenses (for example correctness, then completeness). Out-of-scope findings
   become tracked issues, never silent drops.

## Definition of Done

- Behavior changes ship with tests (unit/integration as appropriate). Handle
  error cases explicitly; never swallow failures (this is the same instinct as
  "fail loudly, never silently coerce").
- `make ci-quick` is green (ruff + mypy strict + pytest).
- Docs are updated when reality changes (README, PLAN, ADRs, this file).
- No secrets in any file; env refs only. No em dashes anywhere.
- Provider SDKs are imported only in `llm/client.py`.

## The merge gate (5 parts)

Merge a PR once: **2 independent adversarial reviews + all bot/review threads
resolved + green CI + aged + a newer PR sits above it.** Aging is relative: merge
the older PR, never the newest. Agents never self-merge; they leave the PR for
Chris. Never `--delete-branch` a stacked base.

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
