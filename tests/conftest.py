"""Shared pytest fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _openai_prices(monkeypatch):
    # OpenAIClient requires explicit per-model prices (no silent default). Set sane
    # test values so any test that constructs the client works; the test that asserts
    # the missing-price failure deletes them explicitly.
    monkeypatch.setenv("OPENAI_PRICE_IN_PER_M", "0.15")
    monkeypatch.setenv("OPENAI_PRICE_OUT_PER_M", "0.60")


@pytest.fixture(autouse=True)
def _anthropic_prices(monkeypatch):
    # AnthropicClient requires explicit per-model prices too (same rule as OpenAI), so
    # constructing it (e.g. via get_client("anthropic")) works; the test that asserts the
    # missing-price failure deletes them explicitly.
    monkeypatch.setenv("ANTHROPIC_PRICE_IN_PER_M", "3.0")
    monkeypatch.setenv("ANTHROPIC_PRICE_OUT_PER_M", "15.0")


@pytest.fixture(autouse=True)
def _no_budget(monkeypatch):
    # Default the per-run budget OFF so a dev's ambient EXTRACT_BUDGET_USD cannot cap
    # unrelated tests. The budget tests inject their own BudgetGuard explicitly.
    monkeypatch.delenv("EXTRACT_BUDGET_USD", raising=False)


@pytest.fixture(autouse=True)
def _gateway_env(monkeypatch):
    # Non-bypass (gateway) mode requires LLM_BASE_URL + LLM_API_KEY; constructing a real
    # client (e.g. via get_client) otherwise fails loud (issue #38). Provide sane defaults
    # so any test that builds a client works; the fail-loud tests delete them explicitly,
    # and GATEWAY_BYPASS / per-test overrides still win where a test sets them.
    monkeypatch.setenv("LLM_BASE_URL", "https://gateway.test")
    monkeypatch.setenv("LLM_API_KEY", "test-gateway-key")
