---
name: safe-slice
description: Turn a request into ONE reviewable implementation slice with explicit verification and minimal collateral change. Use before starting any code change in extract-api.
---

# safe-slice

Ship the narrowest change that moves the work forward and can be reviewed on its
own.

1. **Pick one seam.** The smallest unit that is independently testable (one
   schema, one client path, one endpoint behavior). If the task is bigger,
   propose a split and do the first slice only.
2. **Do not mix layers.** Never combine code changes with strategy-doc or backlog
   edits in the same commit. One commit per logical group.
3. **Verify the exact seam you changed.** Preferred checks:
   - whole gate: `make ci-quick` (ruff + mypy strict + pytest)
   - targeted: `pytest tests/test_<area>.py -q`
   - runs end to end: `make smoke`
4. **Commit small and conventional:** `<area>: <imperative summary>`. Commit
   early; more than ~3 changed files without a commit is a smell.
5. **Respect the invariants:** never silently coerce; provider SDKs only in
   `llm/client.py`; emit `cost_usd`; no secrets; no em dashes.
