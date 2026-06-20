---
name: adversarial-review
description: Run one adversarial review pass on a PR or diff as a single atomic pipeline. Find real defects, fix every severity, and post evidence. Run it twice with different lenses to satisfy the two-review merge gate.
---

# adversarial-review

Execute as ONE atomic task; do not pause between steps.

1. **Review the diff under a named lens** (run 1: correctness; run 2:
   completeness). Classify findings CRITICAL / HIGH / MEDIUM / LOW. Hunt for real
   bugs and for weak tests: tautological assertions, tests that still pass when
   the fix is reverted, missing guard branches and edge cases.
2. **Read ALL existing PR comments** (human and bots: Dependabot, CodeQL,
   gitleaks, prior threads).
3. **Post a findings comment.**
4. **Fix EVERY severity.** There is no "non-blocking" category. Out-of-scope
   findings become tracked issues, never silent drops. Each fix is its own small
   commit referencing the PR.
5. **Push.**
6. **Verify CI is green** (`gh pr checks`).
7. **Post a fix-evidence follow-up** and resolve the threads.

extract-api lenses to apply: strict validation (never silently coerce), the
validation-retry loop (exact failure list, max 2, 422 trail), error-taxonomy
correctness (exactly one per non-200), idempotency (replay / 409 / TTL),
`cost_usd` emission, and the provider-seam isolation. Do NOT merge; leave the PR
for Chris under the 5-part gate.
