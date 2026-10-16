"""The inbound body cap (#142): oversized bodies are refused while being received, before
FastAPI or Pydantic buffer them, and a body under the cap is untouched."""

import json

import anyio
import pytest
from fastapi.testclient import TestClient

from api.main import BodyCap, create_app
from caller_keys import AUTH, TEST_KEY
from llm.client import FixtureClient
from test_extract_endpoint import VALID_JSON

CAP = 10_000
JSON = [(b"content-type", b"application/json")]


@pytest.fixture(autouse=True)
def _small_cap(monkeypatch):
    monkeypatch.setenv("EXTRACT_MAX_BODY_BYTES", str(CAP))
    monkeypatch.setattr("api.main.get_client", lambda provider: FixtureClient(VALID_JSON))


def _body(content: str) -> bytes:
    return json.dumps({"doc_type": "invoice", "content": content}).encode()


def _asgi(app, chunks, *, path="/v1/extract", headers=()):
    """Drive `app` over raw ASGI; return (status, json body, chunks the app pulled)."""
    pulled = 0
    queue = list(chunks)
    sent: list[dict] = []

    async def receive():
        nonlocal pulled
        if not queue:
            return {"type": "http.disconnect"}
        pulled += 1
        return {"type": "http.request", "body": queue.pop(0), "more_body": bool(queue)}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"authorization", f"Bearer {TEST_KEY}".encode()), *headers],
    }
    anyio.run(app, scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    payload = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, json.loads(payload), pulled


def test_content_length_over_the_cap_is_refused_without_reading_the_body():
    status, body, pulled = _asgi(
        create_app(), [b"x"], headers=[(b"content-length", str(CAP + 1).encode())]
    )
    assert status == 422
    assert body["error"] == "validation_failed"
    assert str(CAP) in body["detail"]
    assert pulled == 0


@pytest.mark.parametrize("digits", [b"9" * 5000, b"0" * 5000 + b"1"], ids=["huge", "padded-one"])
def test_absurd_content_length_digits_are_handled_not_a_500(digits):
    # int() raises on more than ~4300 digits; the declared length must fail closed, not 500.
    # 5000 zeros then 1 is a legitimate length of 1 and is not over the cap.
    headers = [*JSON, (b"content-length", digits)]
    status, body, pulled = _asgi(create_app(), [_body("Invoice INV-1")], headers=headers)
    if digits.startswith(b"9"):
        assert (status, body["error"], pulled) == (422, "validation_failed", 0)
    else:
        assert status == 200


def test_chunked_body_over_the_cap_is_refused_mid_stream():
    chunks = [b"x" * 1000] * 1000  # 1 MB offered, no Content-Length
    status, body, pulled = _asgi(create_app(), chunks)
    assert status == 422
    assert body["error"] == "validation_failed"
    assert pulled == CAP // 1000 + 1  # stopped on the first chunk past the cap


def test_understated_content_length_does_not_dodge_the_stream_count():
    chunks = [b"x" * 1000] * 1000
    status, _, pulled = _asgi(create_app(), chunks, headers=[(b"content-length", b"10")])
    assert status == 422
    assert pulled == CAP // 1000 + 1


def _padded_body(size: int) -> bytes:
    raw = _body("Invoice INV-1" + " " * (size - len(_body("Invoice INV-1"))))
    assert len(raw) == size
    return raw


@pytest.mark.parametrize("size, status", [(CAP, 200), (CAP + 1, 422)])
def test_streamed_body_cap_is_inclusive(size, status):
    raw = _padded_body(size)
    chunks = [raw[i : i + 1000] for i in range(0, len(raw), 1000)]  # no Content-Length
    got, body, _ = _asgi(create_app(), chunks, headers=JSON)
    assert got == status
    if status == 422:
        assert str(CAP) in body["detail"]


def test_body_under_the_cap_still_extracts():
    resp = TestClient(create_app(), headers=AUTH).post(
        "/v1/extract", content=_body("Invoice INV-1"), headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["invoice_number"] == "INV-1"


@pytest.mark.parametrize("slack, status", [(0, 200), (-1, 422)])
def test_the_cap_is_inclusive(monkeypatch, slack, status):
    raw = _body("Invoice INV-1")
    monkeypatch.setenv("EXTRACT_MAX_BODY_BYTES", str(len(raw) + slack))
    resp = TestClient(create_app(), headers=AUTH).post(
        "/v1/extract", content=raw, headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == status


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
def test_health_probes_ignore_the_cap(path):
    # A bodyless GET never reaches the cap, so declare an over-cap body: were the probe capped
    # this would be the 422 body verdict; uncapped, the router answers 405 for the method.
    status, body, _ = _asgi(
        create_app(), [b"x"], path=path, headers=[(b"content-length", str(CAP + 1).encode())]
    )
    assert status == 405
    assert "limit" not in json.dumps(body)


def test_unauthenticated_oversized_request_is_a_401_not_a_body_verdict():
    resp = TestClient(create_app()).post("/v1/extract", content=b"x" * (CAP + 1))
    assert resp.status_code == 401


@pytest.mark.parametrize("raw", ["", "0", "-1", "1.5", "big"])
def test_invalid_cap_fails_at_startup(monkeypatch, raw):
    monkeypatch.setenv("EXTRACT_MAX_BODY_BYTES", raw)
    with pytest.raises(ValueError, match="EXTRACT_MAX_BODY_BYTES must be a positive integer"):
        create_app()


def test_default_cap_is_32_mib(monkeypatch):
    monkeypatch.delenv("EXTRACT_MAX_BODY_BYTES")
    (cap,) = [m for m in create_app().user_middleware if m.cls is BodyCap]
    assert cap.kwargs == {"limit": 32 * 1024 * 1024}
