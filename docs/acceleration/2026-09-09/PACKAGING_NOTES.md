# Packaging notes and corrections

## Recovery boundary

The saved artifacts available for this pass contained 26 files. Every recovered
file is included under `source/`. `RECOVERY_INVENTORY.json` records both the original
uploaded-file hash and the packaged hash. Packaging normalises line endings to LF
and replaces em dashes with spaced ASCII hyphens; substantive source content has
not been intentionally changed.

The source files date their review to 4 September 2026. This packaging pass is
9 September 2026. Main was rechecked through GitHub and still pointed to
`aeacafa63685af3b47030375d13b2b5c1d5979f9`. Do not confuse the packaging date with a
new full repository audit.

## Files mentioned previously but not recovered

The earlier README, review and implementation guide refer to a larger planned
bundle. The following were not present in the saved files:

- The 14 invoice and 24 job-posting candidate JSON files. The 38-row review-notes
  CSV is available; it is not a corpus and does not contain full expected labels.
- Complete reference implementation modules, their tests, schemas and example
  manifests beyond the surviving `implementation/PATCH_GUIDE.md`.
- Additional fixture-review/paid-run prompts, issue-comment templates and source
  map files beyond the surviving 26-file inventory.
- The prior bundle validator, manifest, ZIP and interactive HTML deck.

This pass creates a new working deck, manifest, validator, plan renderer, tests
and downloadable ZIP. It does not invent recovered fixture contents or claim
that missing implementation work was completed. Future tasks that reference an
absent path need to create that artifact before they can depend on it.

## Historical claims require revalidation

Treat all source documents, numbers, recommendations, future dates, effort
estimates and issue-disposition proposals as historical review material. There
has been no new paid evaluation. A successful package validation is not evidence
of model accuracy, production readiness, or a successful application test run.
The source assessment scores are judgments, not measured metrics.

The earlier source says local application tests were not run. This pass also did
not run the application's full gate. Access to the repository was through the
GitHub connector; an attempted local Git clone was blocked by unavailable DNS.
The package's own tests are reported separately in `VERIFICATION.md`.

## Authority and execution

The user requested a packaging PR, not implementation, issue closures, paid calls,
fixture promotion, licence changes or merges. None of those operations are part of
this pass. The old bootstrap and task graph contain proposed future operations;
these are not permissions issued by this PR.

Default selections are recommendations only. The new deck starts unanswered.
Choosing recommendations or importing answers never grants run approval, label
certification, safety-control changes, GitHub mutations or merge authority.
When rendering a partial answer set, the new renderer leaves the rest unresolved.
It does not infer task applicability from a default or silently execute the
historical 42-task graph.

Read the live repository's instructions and owner decisions before promoting any
of the five draft ADRs. Do not renumber, replace or accept current ADRs simply
because this package contains drafts with those numbers.

The historical Python scripts are retained under `source/scripts/` for reference.
They are not recommended execution entrypoints. The directory's Ruff exclusion
is limited to archived source material and does not change application lint rules.

## Historical task reference

The issue-seeding manifest references `H09`, which is not in the 42-task graph.
The corresponding human operation is `HT09` in `source/machine/human-tasks.json`.
Reconcile that reference before seeding issues rather than treating it as a valid
executable dependency.
