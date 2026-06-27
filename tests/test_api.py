"""App boots: /healthz is live; /v1/extract is wired (happy + error paths in
test_extract_endpoint.py). Here: liveness, the request boundary, and that the
Anthropic provider path (T09) routes to the real client end-to-end."""

import json
import types

import anthropic
from fastapi.testclient import TestClient

from api.main import create_app
from llm.client import AnthropicClient, get_client


def test_healthz_ok():
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_unknown_route_renders_not_found():
    # Framework routing 404 carries a taxonomy code too (issue #28), not the default body.
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.get("/no-such-route")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_wrong_method_renders_method_not_allowed():
    # GET on the POST-only extract route: a routing 405 carries the taxonomy code AND the
    # RFC-required Allow header (which the taxonomy handler must forward, not drop).
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.get("/v1/extract")
    assert resp.status_code == 405
    assert resp.json()["error"] == "method_not_allowed"
    assert "POST" in resp.headers.get("allow", "")


def test_anthropic_path_routes_to_the_real_client(monkeypatch):
    # T09: a provider="anthropic" request must reach the real AnthropicClient (not the
    # FixtureClient short-circuit, which get_client takes when LLM_PROVIDER_MODE is set)
    # and drive it end-to-end. The SDK is mocked so this stays offline and deterministic.
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    assert isinstance(get_client("anthropic"), AnthropicClient)

    invoice = json.dumps(
        {
            "invoice_number": "INV-9",
            "issue_date": "2026-02-01",
            "due_date": None,
            "currency": "GBP",
            "subtotal_minor": 5000,
            "tax_minor": 1000,
            "total_minor": 6000,
            "vendor_name": "Acme Ltd",
            "vendor_tax_id": None,
            "buyer_name": None,
            "line_items": None,
        }
    )
    message = types.SimpleNamespace(
        content=[types.SimpleNamespace(type="text", text=invoice)],
        stop_reason="end_turn",
        usage=types.SimpleNamespace(input_tokens=10, output_tokens=5),
        model="claude-test",
    )
    monkeypatch.setattr(
        anthropic,
        "Anthropic",
        lambda **kwargs: types.SimpleNamespace(
            messages=types.SimpleNamespace(create=lambda **kwargs: message)
        ),
    )
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.post(
        "/v1/extract",
        json={
            "doc_type": "invoice",
            "schema_version": "v1",
            "content": "x",
            "provider": "anthropic",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["provider"] == "anthropic"
    assert body["meta"]["model"] == "claude-test"
    assert body["data"]["invoice_number"] == "INV-9"


def test_extract_rejects_unknown_doc_type_at_boundary():
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.post(
        "/v1/extract",
        json={"doc_type": "passport", "schema_version": "v1", "content": "x"},
    )
    # An out-of-Literal doc_type is a RequestValidationError; the T05 handler renders it
    # as the taxonomy's unsupported_doc_type, not FastAPI's default 422 body.
    assert resp.status_code == 422
    assert resp.json()["error"] == "unsupported_doc_type"
