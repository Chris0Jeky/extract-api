# Git workflow (safe vs blocked)

Solo repo, agent-driven. The shared cross-runtime deny floor `.claude/hooks/dispatch.py`
(canonical: agent-harness, tier-aware) is vendored but not wired by the committed settings,
and no Claude floor runs on DESKTOP-IHKOOJS, so the blocked rows below are held by the agent;
the legacy `scripts/agent_hooks/pre_tool_use.py` regex floor is retained only for its
tests pending retirement. The table below is the rationale.

| Action | Status | Note |
| --- | --- | --- |
| `git add` / `git commit` | safe | small, conventional, per logical group |
| `git switch -c <type>/<desc>` | safe | branch before the first product change |
| `git push` (normal) | safe | T2 authority: publishing a scoped branch is free |
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
- Push and merge authority is declared in `.agent-harness/tier.json`, not here.

## Agent operating notes

Hook-related notes below describe behavior only when a safety hook is actively
configured. The committed settings in this repo do not wire the vendored floor;
these notes do not establish runtime interception.

- An active safety hook may inspect the whole Bash command string, including
  quoted prose. For multiline commit messages, PR bodies, issue bodies, and review
  replies, write the exact text to a file and use `git commit -F file` or
  `gh ... --body-file file`. This also preserves newlines and avoids shell quoting
  errors. Body files do not exempt an operation from review or authorization.
- **Run the full `uv run make ci-quick` as its own step before every push.**
  Verify the gate, then push. If an active hook rejects a compound command, do not
  assume any earlier formatting or verification step in that command ran.
- **Stacked merges under strict branch protection:** merge oldest-first; after each
  merge, `gh pr edit N --base main` to retarget the next PR (it is not auto-retargeted
  while the old base branch still exists), then `gh pr update-branch N` so CI re-runs,
  then merge. Use a `git worktree` to fix a lower PR while a review reads another tree.
