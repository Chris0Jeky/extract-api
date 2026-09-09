# Package verification

Packaging date: 9 September 2026. Application baseline: aeacafa63685af3b47030375d13b2b5c1d5979f9.

## Completed checks

- `node --test tools/bundle.test.mjs`: 14 tests passed on Node 22.16.0.
- Catalog integrity: all 20 decisions have unique IDs, valid recommendations and
  valid default selections. The generated deck embeds the same catalog.
- Task integrity: all 42 proposed tasks have unique IDs, resolvable dependencies
  and an acyclic dependency graph.
- Recovery integrity: all 26 recovered files match their packaged SHA-256 hashes.
- Manifest validation checks the exact file set, byte lengths and SHA-256 hashes.
  Its negative tests detect changed files and unlisted extra files.
- Handoff tests reject wrong repository/snapshot, unknown options, malformed notes
  and oversized notes. Partial answers are not filled with defaults.

## Browser interaction checks

Chromium through Playwright completed 14 checks: initial 0/20 progress, notes,
partial JSON export, recommendations preserving custom answers, unanswered filter,
search, safe rendering of HTML-like notes, import/export round trip, invalid-import
rollback, Markdown export, 390px mobile layout without horizontal overflow,
next/previous navigation, reset, and no page errors or external asset requests.
Desktop and mobile screenshots were visually inspected.

The browser environment blocked file:// and localhost navigation with
ERR_BLOCKED_BY_ADMINISTRATOR. The generated HTML was therefore rendered inline
using Playwright's `set_content`. LocalStorage is unavailable in that test origin;
the storage-failure notice was exercised, but persistence across real file-origin
reloads was not verified. JSON export/import remains the tested durable handoff.

## Scope limits

These checks verify the package, not model accuracy or the extraction service.
No live provider call, fixture promotion, application source change or full
application gate was run in this pass. A local Git clone attempt failed because
GitHub DNS was unavailable in the container. GitHub connector reads confirmed
that the target main branch still matches the review snapshot.

The PR's application CI must be read separately. This file does not pre-claim
that remote CI passed. Hashes detect drift; they are not an authenticity signature.
