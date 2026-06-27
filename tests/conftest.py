"""Shared pytest fixtures."""

import os
import tempfile
from pathlib import Path

import pytest

# api.main builds the default idempotency store at import (`app = create_app()`), and any
# test that calls create_app() without injecting a store builds one too. Default the db
# path into the system temp dir so those never litter the repo working tree. Tests that
# exercise idempotency inject their own tmp_path store for isolation.
os.environ.setdefault(
    "IDEMPOTENCY_DB_PATH", str(Path(tempfile.gettempdir()) / "extract_api_test_idem.sqlite")
)


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
