# Git workflow (safe vs blocked)

Solo repo, agent-driven. The harness enforces most of this via
`scripts/agent_hooks/pre_tool_use.py`; the table is the rationale.

| Action | Status | Note |
| --- | --- | --- |
| `git add` / `git commit` | safe | small, conventional, per logical group |
| `git switch -c <type>/<desc>` | safe | branch before the first product change |
| `git push` (normal) | safe with approval | no push without Chris's explicit go |
| `git push --force` (bare) | BLOCKED | rewrites remote history destructively |
| `git push --force-with-lease` | allowed if needed | only to fix your own just-pushed branch |
| `git reset --hard` | BLOCKED on shared work | explain before discarding anything |
| `git checkout -- <file>` | discouraged | discards changes; explain first |
| `rm -rf /`, `rm -rf ~` | BLOCKED | never |
| `--delete-branch` a stacked base | BLOCKED | breaks the stack (merge gate) |

Rules:

- Never bare force-push. If you must rewrite remote history on your own branch,
  use `--force-with-lease` and say why.
- Before deleting or overwriting anything you did not create, look at it and
  surface what you find instead of proceeding.
- No push without explicit approval. A remote exists; that does not change this.

## Agent operating notes (learned the hard way)

- **The safety hook inspects the whole Bash command string, not intent.** A commit
  message, PR body, issue body, or review reply that merely *describes* `rm -rf /`,
  `curl ... | sh`, `sudo`, a force-push, or a secret will be blocked. Write that text
  to a file and pass it via `git commit -F file`, `gh ... -F body=@file`, or
  `--body-file`. The editor/Write tool bypasses the hook.
- **Run the full `make ci-quick` as its own step before every push.** A compound
  `ruff format && ... && git push` that gets blocked mid-way skips the format step,
  and CI then fails on an unformatted file. Verify the gate, then push.
- **Stacked merges under strict branch protection:** merge oldest-first; after each
  merge, `gh pr edit N --base main` to retarget the next PR (it is not auto-retargeted
  while the old base branch still exists), then `gh pr update-branch N` so CI re-runs,
  then merge. Use a `git worktree` to fix a lower PR while a review reads another tree.
