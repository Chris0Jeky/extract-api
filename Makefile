# extract-api developer interface. Fail loud: every target runs its tool and
# fails on a non-zero exit. No error swallowing (no `2>/dev/null || echo ...`).
#
# PYTHON points at the interpreter. With uv: `uv run make <target>` or activate
# the venv. Override directly, e.g. `make PYTHON=.venv/Scripts/python test`.
PYTHON ?= python
PORT ?= 8200

.DEFAULT_GOAL := help

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

dev: ## Run the API locally (uvicorn, autoreload)
	$(PYTHON) -m uvicorn api.main:app --reload --port $(PORT)

test: ## Run pytest with coverage (ratchet floor in pyproject)
	$(PYTHON) -m pytest

typecheck: ## Run mypy in strict mode
	$(PYTHON) -m mypy

lint: ## Ruff lint + format check
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format: ## Apply ruff format + import sort + safe fixes
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .

ci-quick: lint typecheck test ## Pre-push gate: lint + types + tests

smoke: ## Deterministic offline smoke (no paid model calls)
	$(PYTHON) scripts/smoke.py

accuracy-run: ## Run the accuracy harness (pending M3: T16/T17)
	@echo "accuracy-run: pending M3 (T16/T17); no REVIEWED fixtures scored yet."

fixtures-validate: ## Validate fixtures against their schema + label rules
	$(PYTHON) scripts/validate_fixtures.py

test-hooks: ## Self-test the agent safety hooks
	$(PYTHON) scripts/agent_hooks/smoke_test.py

.PHONY: help dev test typecheck lint format ci-quick smoke accuracy-run fixtures-validate test-hooks
