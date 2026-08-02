# ADR 0001: Pinned dependency versions and runtime

- Status: ACCEPTED (2026-06-13). This amendment records the lockfile hardening for issue #6.
- Deciders: Chris.

## Context

extract-api is a fail-loud service; reproducibility is part of the contract. The
standing rule is "verify dependency versions from official docs at build time,
never from memory." All versions below were fetched live from PyPI JSON and
confirmed against official docs on 2026-06-13, and confirmed again by the
resolved install.

## Decision

Pin the following. A committed `uv.lock` is now the authoritative reproducibility
record (issue #6): it holds the exact resolved versions, always within the ranges
declared in `pyproject.toml`. The table below is the original 2026-06-13 verification
snapshot, kept for provenance; its ranges and versions predate later Dependabot bumps,
so consult `pyproject.toml` (current ranges) and `uv.lock` (current pins) for today's
values:

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
pydantic. A universal `uv.lock` (`requires-python >=3.12,<3.14`, resolved across
platforms) is committed and is the reproducibility record. CI installs frozen from
it (`uv sync --locked --extra dev`), and the Docker runtime uses uv 0.11.21 with
`uv sync --locked --no-dev --no-editable --python 3.13`. A lock that has drifted
from pyproject therefore fails either install path loudly rather than resolving
silently. Regenerate it with `make lock` (`uv lock`)
after any dependency change and commit the result; Dependabot (uv ecosystem) updates
the lock and pyproject together. The verified table above therefore records the
original snapshot, not the current pins, which live in `uv.lock`. Plain `venv` + pip
(`pip install -e ".[dev]"`) remains the documented unpinned fallback for local dev.

**Runtime:** `requires-python = ">=3.12,<3.14"`; the dev venv is built on Python
3.13. The `<3.14` ceiling avoids C-extension wheel lag (PyMuPDF, pydantic-core)
until 3.14 wheels are confirmed.

**Package manager:** uv (`uv venv`, `uv sync`, `uv lock`). `uv.lock` is committed
and frozen in CI (issue #6). Plain `venv` + pip is the documented local fallback.

## Consequences

- Tight pins on the pre-1.0 packages (`fastapi`, `anthropic`, `ruff`) trade some
  freshness for reproducible behavior; upgrades are deliberate PRs (Dependabot
  proposes, CI gates).
- The frozen lock is the tripwire: editing a dependency in pyproject without running
  `make lock` leaves the lock drifted, and `uv sync --locked` fails CI loudly. This
  is deliberate (fail loud over silent re-resolution). The cost is one `make lock`
  step per dependency change, which Dependabot performs automatically.
- The provider SDKs evolve fast (structured-output APIs especially, see ADR
  0002); revisit at each milestone.
