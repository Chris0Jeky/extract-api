# AGENTS.md

Authoritative rulebook for anyone (human or agent) working in extract-api.
`CLAUDE.md` is the orientation (map, proving checks, pitfalls, locked decisions)
and defers to this file. Precedence: an explicit instruction from Chris > this
file > inline code comments.

Review, merge, and commit policy has one home: the twelve global laws in
`~/.claude/rules/laws.md` (Codex: `~/.codex/AGENTS.md`), applied at this repo's declared tier (**T2**,
`.agent-harness/tier.json`). Nothing here restates it.

## Review lenses specific to this repo

Carry these into whatever review the tier calls for:

- Strict validation: never silently coerce, never guess an absent value.
- The validation-retry loop: exact failure list appended, max 2 attempts, full
  trail in the 422.
- Error-taxonomy correctness: exactly one code per non-200; `api/errors.py` is the
  source of truth.
- Idempotency: replay on key+hash match, 409 on mismatch, 24h TTL.
- `cost_usd` emitted and env-priced, never silently defaulted.
- Provider-seam isolation: a provider SDK only in `llm/client.py`.

## Definition of Done

- Behavior changes ship with tests. Handle error cases explicitly; never swallow
  a failure (the same instinct as "fail loudly, never silently coerce").
- `make ci-quick` is green (ruff + mypy strict + pytest), plus the narrowest seam
  check from the CLAUDE.md proving-checks table.
- Docs updated when reality changes (README, PLAN, ADRs, `docs/STATUS.md`, this
  file). One reviewable slice per PR; do not mix code with strategy-doc changes.
- No secrets in any file; env refs only. No em dashes anywhere.

## Security baseline

- No secrets committed; ship `.env.example` only. `gitleaks` scans every PR.
- The runtime guard: the vendored floor `.claude/hooks/dispatch.py` is not wired by the committed settings (no `PreToolUse` hook) and no Claude floor runs on DESKTOP-IHKOOJS, so nothing enforces command safety at runtime: act as if nothing catches an irreversible command. `.claude/settings.json` keeps a small permission-level
  deny tripwire. The vendored copy holds canonical bytes from agent-harness: do not edit it here; sync it from
  upstream. Repo git conventions: `docs/agentic/GIT_WORKFLOW.md`.
