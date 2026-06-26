"""App boots: /healthz is live; /v1/extract is wired (happy + error paths in
test_extract_endpoint.py). Here: liveness, the request boundary, and the one
provider path still pending (Anthropic, T09)."""

from fastapi.testclient import TestClient

from api.main import create_app
from llm.client import AnthropicClient, get_client


def test_healthz_ok():
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_anthropic_path_not_implemented_yet_fails_loudly(monkeypatch):
    # The endpoint is wired, but the Anthropic real-call client still raises
    # NotImplementedError until T09; it surfaces as a 500, not a silent success.
    # Pin routing: get_client short-circuits to FixtureClient when LLM_PROVIDER_MODE
    # is set, which would make this 500 for the wrong reason. Delete it and assert the
    # request actually routes to AnthropicClient so the cause is unambiguous.
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    assert isinstance(get_client("anthropic"), AnthropicClient)
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
    assert resp.status_code == 500


def test_extract_rejects_unknown_doc_type_at_boundary():
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.post(
        "/v1/extract",
        json={"doc_type": "passport", "schema_version": "v1", "content": "x"},
    )
    # FastAPI request validation rejects an out-of-Literal doc_type before our code.
    assert resp.status_code == 422
