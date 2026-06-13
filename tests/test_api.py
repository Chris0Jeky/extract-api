"""App boots: /healthz is live; /v1/extract is a stub until M1."""

from fastapi.testclient import TestClient

from api.main import create_app


def test_healthz_ok():
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_extract_is_stub_until_m1():
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.post(
        "/v1/extract",
        json={"doc_type": "invoice", "schema_version": "v1", "content": "x", "provider": "default"},
    )
    # The pipeline is a NotImplementedError stub; it surfaces as a 500 for now.
    assert resp.status_code == 500


def test_extract_rejects_unknown_doc_type_at_boundary():
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.post(
        "/v1/extract",
        json={"doc_type": "passport", "schema_version": "v1", "content": "x"},
    )
    # FastAPI request validation rejects an out-of-Literal doc_type before our code.
    assert resp.status_code == 422
