# extract-api acceleration handoff

Packaged on 9 September 2026 for `Chris0Jeky/extract-api`.
Reviewed and rechecked base: `aeacafa63685af3b47030375d13b2b5c1d5979f9`.

This directory contains all **26 recovered files** from the earlier review, plus
an offline decision studio, a safe handoff renderer and integrity checks. It is
planning and reference material. It does not change the API, accepted ADRs,
fixtures, dependencies, GitHub settings or agent safety controls.

## Start here

Open [decision-deck/index.html](decision-deck/index.html) in a local browser after
checking out this PR or extracting the downloadable bundle. GitHub displays HTML
source rather than running the studio. The HTML is self-contained and makes no
network requests. No server or package installation is needed to use it.

The studio contains all 20 recovered decisions, with context, trade-offs,
recommendations, notes, answer filters and JSON/Markdown export. It saves answers
in browser storage when available; export JSON before moving the file or changing
browsers. Unanswered questions remain unresolved. Import validates the repository,
snapshot, decision IDs and option IDs before replacing any answers.

Give the exported `extract-api-agent-handoff.json`, this directory and
[START_AGENT.md](START_AGENT.md) to the in-repo agent. There is nothing to unbundle
inside the checkout: the reference files are already under `source/`.

## Contents

| Location | Contents |
| --- | --- |
| `source/MASTER_REVIEW.md` | Full earlier project review and architecture assessment |
| `source/review/` | Issue triage, risks, edge cases and documentation drift |
| `source/machine/` | 20 decisions, 42 proposed tasks, issue suggestions, risks and human tasks |
| `source/decisions/` | Five draft ADRs, not accepted repository decisions |
| `source/implementation/PATCH_GUIDE.md` | Implementation guidance and references |
| `source/roadmap/` | Critical path and 30/60/90-day proposal |
| `source/prompts/`, `source/AGENT_BOOTSTRAP.md` | Historical agent handoff instructions |
| `source/candidate-fixtures/review-notes.csv` | Review notes for 38 proposed fixture IDs; no fixture JSONs were recovered |
| `decision-deck/` | Newly completed offline decision studio |
| `tools/` | Dependency-free build, validation, plan rendering and tests |
| `RECOVERY_INVENTORY.json` | Original and packaged hashes for all 26 recovered files |
| `BUNDLE_MANIFEST.json` | File inventory and SHA-256 integrity checks for this package |

## Important corrections to the earlier handoff

Read [PACKAGING_NOTES.md](PACKAGING_NOTES.md) before using the historical files.
Their original README describes several files that were not present in the saved
artifacts. Those descriptions are preserved as historical material, not repeated
as claims about this package. In particular, **the 38 candidate fixture JSONs and
complete reference implementation modules were not recovered**. Only their notes
and implementation guide are available. The agent must generate missing material
as new work, not assume it has already been implemented or validated.

The old renderer in `source/scripts/` silently fills missing decisions with defaults.
Use the new renderer below instead. It preserves unresolved decisions and does not
turn planning choices into authority to spend money, certify labels or merge code.

## Verify and render

The tooling requires Node.js 18 or newer and uses only built-in modules:

```sh
node tools/bundle.mjs validate
node --test tools/bundle.test.mjs
node tools/bundle.mjs plan /path/to/extract-api-agent-handoff.json /path/to/ACTIVE_PLAN.md
```

The output path must not already exist. The plan renderer never calls GitHub,
providers or a shell and never edits application source. The recovered task graph
is advisory: reconcile it with selected decisions and current repository state
before executing any task. Do not run all 42 tasks blindly.

To rebuild the generated HTML or intentionally update checksums after reviewed edits:

```sh
node tools/build-deck.mjs
node tools/bundle.mjs manifest
node tools/bundle.mjs validate
```

A hash manifest detects accidental drift, not a malicious change by someone who
can edit both payload and manifest. See [VERIFICATION.md](VERIFICATION.md) for the
checks actually performed. No paid extraction or application change is authorised
by this package. The PR is intended to remain open for review.
