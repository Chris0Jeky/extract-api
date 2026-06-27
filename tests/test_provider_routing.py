"""Provider selection routing (T10), end-to-end through POST /v1/extract.

The endpoint resolves the client via get_client(request.provider) and the pipeline
drives it. These tests assert the FULL routing matrix reaches the right concrete
client - proven by meta.provider, the resolved client's own provider tag - for:
explicit openai, explicit anthropic, default with no env (-> openai), and default
with LLM_DEFAULT_PROVIDER=anthropic. Both SDKs are mocked so this stays offline and
deterministic; get_client itself is NOT monkeypatched, so the real routing runs.
"""

from __future__ import annotations

import json
import types

import anthropic
import openai
from fastapi.testclient import TestClient

from api.main import create_app

_INVOICE = json.dumps(
    {
        "invoice_number": "INV-1",
        "issue_date": "2026-01-15",
        "due_date": None,
        "currency": "GBP",
        "subtotal_minor": 10000,
        "tax_minor": 2000,
        "total_minor": 12000,
        "vendor_name": "Acme Ltd",
        "vendor_tax_id": None,
        "buyer_name": None,
        "line_items": None,
    }
)


def _mock_openai(monkeypatch, *, model="gpt-test"):
    """Patch openai.OpenAI to return a canned valid-invoice response."""
    response = types.SimpleNamespace(
        output_text=_INVOICE,
        status="completed",
        incomplete_details=None,
        usage=types.SimpleNamespace(input_tokens=10, output_tokens=5),
        output=[],
        model=model,
        error=None,
    )
    monkeypatch.setattr(
        openai,
        "OpenAI",
        lambda **kwargs: types.SimpleNamespace(
            responses=types.SimpleNamespace(create=lambda **kwargs: response)
        ),
    )


def _mock_anthropic(monkeypatch, *, model="claude-test"):
    """Patch anthropic.Anthropic to return a canned valid-invoice message."""
    message = types.SimpleNamespace(
        content=[types.SimpleNamespace(type="text", text=_INVOICE)],
        stop_reason="end_turn",
        usage=types.SimpleNamespace(input_tokens=10, output_tokens=5),
        model=model,
    )
    monkeypatch.setattr(
        anthropic,
        "Anthropic",
        lambda **kwargs: types.SimpleNamespace(
            messages=types.SimpleNamespace(create=lambda **kwargs: message)
        ),
    )


def _post(provider):
    client = TestClient(create_app(), raise_server_exceptions=False)
    return client.post(
        "/v1/extract",
        json={"doc_type": "invoice", "schema_version": "v1", "content": "x", "provider": provider},
    )


def test_explicit_openai_routes_to_openai(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    _mock_openai(monkeypatch)
    resp = _post("openai")
    assert resp.status_code == 200
    assert resp.json()["meta"]["provider"] == "openai"


def test_explicit_anthropic_routes_to_anthropic(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    _mock_anthropic(monkeypatch)
    resp = _post("anthropic")
    assert resp.status_code == 200
    assert resp.json()["meta"]["provider"] == "anthropic"


def test_default_falls_back_to_openai(monkeypatch):
    # No LLM_DEFAULT_PROVIDER -> default resolves to openai (the locked decision).
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    monkeypatch.delenv("LLM_DEFAULT_PROVIDER", raising=False)
    _mock_openai(monkeypatch)
    resp = _post("default")
    assert resp.status_code == 200
    assert resp.json()["meta"]["provider"] == "openai"


def test_default_resolves_via_env_to_anthropic(monkeypatch):
    # LLM_DEFAULT_PROVIDER=anthropic -> default resolves to anthropic.
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    monkeypatch.setenv("LLM_DEFAULT_PROVIDER", "anthropic")
    _mock_anthropic(monkeypatch)
    resp = _post("default")
    assert resp.status_code == 200
    assert resp.json()["meta"]["provider"] == "anthropic"


def test_fixture_mode_short_circuits_provider_selection(monkeypatch):
    # LLM_PROVIDER_MODE=fixture overrides selection entirely: any provider resolves to
    # the FixtureClient, which returns the canned text without touching a real SDK.
    monkeypatch.setenv("LLM_PROVIDER_MODE", "fixture")
    monkeypatch.setenv("FIXTURE_CANNED_TEXT", _INVOICE)
    resp = _post("anthropic")
    assert resp.status_code == 200
    assert resp.json()["meta"]["provider"] == "fixture"
