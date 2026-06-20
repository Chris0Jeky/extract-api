---
name: pre-merge-gate
description: Final pre-merge validation for a PR. Check bot comments, run the local gate, self-review, confirm CI is green, and emit a merge-readiness report. It validates only; it never merges.
---

# pre-merge-gate

1. **Bot + comment check:** every thread (human and bot) is resolved, or replied
   to with invalidation evidence, or seeded as a tracked issue. Tech debt zero.
2. **Local gate:** `make ci-quick` is green; `make smoke` passes.
3. **Self-review checklist:**
   - no secrets, no debug prints, no leftover TODO without an issue;
   - behavior change ships with tests; no swallowed failures;
   - provider SDKs only in `llm/client.py`; `cost_usd` still emitted;
   - small conventional commits; no em dashes.
4. **CI:** `gh pr checks` shows the required `quality` job green.
5. **Report merge-readiness** against the 5-part gate (two adversarial reviews +
   threads resolved + green CI + aged + a newer PR above it).

Do NOT merge the PR. Validate and report; leave the merge to Chris.
