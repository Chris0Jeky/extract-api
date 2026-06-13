# Human operations (GitHub UI steps agents cannot do)

These require repo-admin access in the GitHub UI. Do them once; record the date.

## Branch protection on `main`

- Require a pull request before merging (a single self-review is fine on a solo
  repo).
- Require status checks to pass before merging, and require branches to be up to
  date. Required check: **`lint + types + tests`** (the `quality` job in
  `.github/workflows/ci.yml`). Mark `secret scan (gitleaks)` required too once it
  is confirmed green on this repo.
- Do not allow bypassing the above.

## Auto-merge

- Enable "Allow auto-merge" (Settings -> General) so
  `dependabot-auto-merge.yml` can complete patch/minor dev+transitive bumps once
  CI is green. Allow GitHub Actions to approve pull requests if you want the
  auto-approve step to function.

## Hardening follow-ups

- **Pin action SHAs.** `ci.yml` and `dependabot-auto-merge.yml` currently use
  version tags. Before the repo is public, pin each `uses:` to a commit SHA with
  a `# vX` comment. Dependabot's `github-actions` updates keep them current.
- **gitleaks.** Free for personal/public repos; confirm the first run is green.
  For org use, add a `GITLEAKS_LICENSE` secret.

## The merge gate (manual discipline)

CI enforces "green". The rest of the 5-part gate is manual: two adversarial
reviews, all threads resolved, the PR aged (merge the older one, never the
newest, once a newer PR sits above it). See `AGENTS.md`.
