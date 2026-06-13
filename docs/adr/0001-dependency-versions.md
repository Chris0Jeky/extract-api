# ADR 0001: Pinned dependency versions and runtime

- Status: ACCEPTED (2026-06-13).
- Deciders: Chris.

## Context

extract-api is a fail-loud service; reproducibility is part of the contract. The
standing rule is "verify dependency versions from official docs at build time,
never from memory." All versions below were fetched live from PyPI JSON and
confirmed against official docs on 2026-06-13, and confirmed again by the
resolved install.

## Decision

Pin the following (pyproject ranges; the lockfile carries exact resolved versions):

| Package | Pin | Verified |
| --- | --- | --- |
| `pydantic` | `>=2.13,<3` | 2.13.4 (2026-05-06) |
| `fastapi` | `>=0.136,<0.137` | 0.136.3 (2026-05-23) |
| `openai` | `>=2.41,<3` | 2.41.1 (2026-06-10) |
| `anthropic` | `>=0.109,<0.110` | 0.109.1 (2026-06-09) |
| `PyMuPDF` | `==1.27.2.3` | 1.27.2.3 (2026-04-24) |
| `pytest` | `==9.0.3` | 9.0.3 (2026-04-07) |
| `ruff` | `==0.15.17` | 0.15.17 (2026-06-11) |
| `mypy` | `==2.1.0` | 2.1.0 (2026-05-11) |

`fastapi[standard]` pulls Starlette and Uvicorn; `pydantic-core` rides with
pydantic. The lockfile is the reproducibility guarantee; pyproject ranges are the
human-readable intent.

**Runtime:** `requires-python = ">=3.12,<3.14"`; the dev venv is built on Python
3.13. The `<3.14` ceiling avoids C-extension wheel lag (PyMuPDF, pydantic-core)
until 3.14 wheels are confirmed.

**Package manager:** uv (`uv venv`, `uv pip`, `uv.lock`). Plain `venv` + pip is
the documented fallback and is what the current dev box uses.

## Consequences

- Tight pins on the pre-1.0 packages (`fastapi`, `anthropic`, `ruff`) trade some
  freshness for reproducible behavior; upgrades are deliberate PRs (Dependabot
  proposes, CI gates).
- The provider SDKs evolve fast (structured-output APIs especially, see ADR
  0002); revisit at each milestone.
