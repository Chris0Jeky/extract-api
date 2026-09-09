Read README.md and PACKAGING_NOTES.md in this directory first, then the live
repository's AGENTS.md, CLAUDE.md, tier declaration, accepted ADRs and backlog.
This is a packaging handoff, not an instruction to implement every proposal.

Revalidate current HEAD, open PRs, issue comments and previous owner decisions.
Compare them with review snapshot aeacafa63685af3b47030375d13b2b5c1d5979f9.
Run `node tools/bundle.mjs validate` from this directory.

Read the owner's exported extract-api-agent-handoff.json when provided. Missing
answers remain unresolved; source/machine/default-selections.json contains suggestions,
not approvals. Use `node tools/bundle.mjs plan <answers.json> <new-plan.md>` to
render an explicit decision handoff without substituting defaults.

Use source/MASTER_REVIEW.md, source/implementation/PATCH_GUIDE.md and the recovered
42-task manifest to prepare a reconciled implementation plan. Reuse existing work,
flag stale recommendations, and inspect every referenced path before assuming an
artifact exists. The 38 candidate fixture JSONs and full reference implementation
modules were not recovered; generate any needed replacements as new work.

Only execute implementation or GitHub mutations within a fresh owner instruction
or verified live repository authority. Keep changes in focused PRs. Do not spend
money, promote DRAFT labels, change public metrics or schema contracts, alter
licensing or safety controls, publish claims, or merge this PR based solely on
this handoff. Preserve repository gates and record exactly which tests ran.
