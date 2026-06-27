"""App boots: /healthz is live; /v1/extract is wired (happy + error paths in
test_extract_endpoint.py; provider routing in test_provider_routing.py). Here:
liveness and the request boundary."""

from fastapi.testclient import TestClient

from api.main import create_app


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
