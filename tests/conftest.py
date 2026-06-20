"""Shared pytest fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _openai_prices(monkeypatch):
    # OpenAIClient requires explicit per-model prices (no silent default). Set sane
    # test values so any test that constructs the client works; the test that asserts
    # the missing-price failure deletes them explicitly.
    monkeypatch.setenv("OPENAI_PRICE_IN_PER_M", "0.15")
    monkeypatch.setenv("OPENAI_PRICE_OUT_PER_M", "0.60")
