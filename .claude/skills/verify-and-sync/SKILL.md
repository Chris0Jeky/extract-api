---
name: verify-and-sync
description: Close out a piece of work. Verify the changed seam by actually running it, sync only the status artifacts whose truth changed, and emit the session handoff. Use at the end of a working session or before opening a PR.
---

# verify-and-sync

1. **Verify the changed seam for real.** Run the command that exercises it and
   read the output. Do not claim tests passed unless they actually ran. State the
   exact commands and their results.
2. **Sync only what changed.** Update the status artifacts whose truth actually
   moved (README numbers, PLAN, BACKLOG task state, ADRs). Do not touch unrelated
   docs.
3. **Emit the handoff** in this fixed shape:

```
## Changed
## Verified            (commands run + results)
## Not verified        (and why)
## Failures / workarounds
## Status sync         (which docs/tasks were updated)
## Next slice          (the next unblocked task, with its id)
```

This is the same session-report shape the project protocol requires: done /
decisions needed / next unblocked tasks.
