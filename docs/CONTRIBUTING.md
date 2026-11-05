# Contributing to extract-api

The rules of record are in `AGENTS.md`; this is the practical how-to.

## Setup

```
uv sync --locked --extra dev
uv run make ci-quick         # ruff + mypy strict + pytest
```

## Branches and commits

- Branch off `main`: `<type>/<short-description>` with type in
  `feat|fix|refactor|test|chore|docs` (for example `feat/idempotency-store`).
- Commits are small, focused, and conventional: `<area>: <imperative summary>`
  (for example `feat(schemas): add salary cross-field validator`). One commit per
  logical group; commit early and often.
- No em dashes anywhere. No secrets (env refs only).

## Tests (near-TDD)

- Behavior changes ship with tests. Make a new test fail when its fix is reverted
  (mutation-verify); never write tautological assertions; write a characterisation
  test before changing existing behavior.
- Coverage has a ratchet floor in `pyproject.toml` (`--cov-fail-under`): it may
  rise, never fall. Raise stricter per-module targets for `schemas/`
  and `llm/client.py` as they gain logic.
- A red build always means a real problem. Quarantine a flake (pytest marker)
  within 24h rather than letting it erode the signal.

## Pull requests

- Fill in the PR template (Summary, Type, Checklist, Risk Notes, Test plan).
- Run `uv run make ci-quick` and the narrowest seam check from the CLAUDE.md
  proving-checks table before opening; add a manual check when the change touches
  the serving path (`docs/testing/MANUAL_VERIFICATION.md`).
- Review, gate, and merge-style policy lives once, in the global laws (AGENTS.md
  names where). Squash merging is disabled on the remote, so it is not a choice
  you have to make here.

## Running the service

```
uv run make dev          # uvicorn on http://127.0.0.1:8200 (/docs for the OpenAPI UI)
uv run make smoke        # deterministic offline smoke, no paid model calls
```
