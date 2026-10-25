"""Real SDK HTTP transports, temporary SQLite and synthetic documents only.

The local HTTP/1.1 provider deliberately keeps connections alive. Disabling cyclic
GC in the resource regression makes ownership deterministic: a completed request
must close its socket without waiting for an unrelated garbage collection cycle.
"""

from __future__ import annotations

import base64
import gc
import json
import socket
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pymupdf
import pytest
import uvicorn
from fastapi.testclient import TestClient

from api.idempotency import SqliteIdempotencyStore
from api.main import create_app
from caller_keys import AUTH

VALID = {
    "invoice_number": "TEST-1",
    "issue_date": "2026-01-15",
    "due_date": None,
    "currency": "GBP",
    "subtotal_minor": 100,
    "tax_minor": 20,
    "total_minor": 120,
    "vendor_name": "Synthetic Test Vendor",
    "vendor_tax_id": None,
    "buyer_name": None,
    "line_items": None,
}


class LocalProvider(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        self.steps = deque()
        self.requests = []
        self.closed = threading.Event()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.barrier = threading.Barrier(2)
        super().__init__(("127.0.0.1", 0), ProviderHandler)


class ProviderHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def finish(self):
        try:
            super().finish()
        finally:
            self.server.closed.set()

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(request)
        step = self.server.steps.popleft() if self.server.steps else "valid"
        self.server.entered.set()
        if step == "barrier":
            self.server.barrier.wait(timeout=3)
        if step in {"timeout", "hold"}:
            self.server.release.wait(5)
        if step == "error":
            self._reply(500, {"error": {"type": "server_error", "message": "synthetic failure"}})
            return
        record = {**VALID}
        if step == "invalid":
            record["total_minor"] = 999
        text = json.dumps(record)
        if self.path.endswith("/responses"):
            part = {"type": "output_text", "text": text, "annotations": []}
            status = "completed"
            if step == "refusal":
                part = {"type": "refusal", "refusal": "synthetic refusal"}
            if step == "cancelled":
                status = "cancelled"
            response = {
                "id": "test-response",
                "object": "response",
                "created_at": 0,
                "model": "test-model",
                "status": status,
                "output": [{"type": "message", "role": "assistant", "content": [part]}],
                "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            }
        else:
            response = {
                "id": "test-message",
                "type": "message",
                "role": "assistant",
                "model": "test-model",
                "content": [{"type": "text", "text": text}],
                "stop_reason": "refusal" if step == "refusal" else "end_turn",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            }
        self._reply(200, response)

    def _reply(self, status, response):
        body = json.dumps(response).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # Expected when the timeout test has already closed the connection.
            self.close_connection = True


@pytest.fixture
def local_provider(monkeypatch):
    server = LocalProvider()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("LLM_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1")
    monkeypatch.setenv("LLM_API_KEY", "synthetic-provider-key")
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_S", "0.2")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("ANTHROPIC_MODEL", "test-model")
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    monkeypatch.delenv("GATEWAY_BYPASS", raising=False)
    try:
        yield server
    finally:
        server.release.set()
        gc.collect()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


@contextmanager
def without_cyclic_gc():
    enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if enabled:
            gc.enable()
        gc.collect()


def post(client, provider="openai", *, key="test-key", **overrides):
    body = {"doc_type": "invoice", "content": "Synthetic invoice", "provider": provider}
    body.update(overrides)
    return client.post("/v1/extract", json=body, headers={"Idempotency-Key": key})


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize(
    "step, status", [("valid", 200), ("refusal", 502), ("error", 502), ("timeout", 504)]
)
def test_provider_request_closes_keepalive_socket_without_cyclic_gc(
    local_provider, tmp_path, provider, step, status
):
    store = SqliteIdempotencyStore(str(tmp_path / "idem.sqlite"))
    local_provider.steps.append(step)
    with TestClient(create_app(idempotency_store=store), headers=AUTH) as client:
        with without_cyclic_gc():
            response = post(client, provider)
            local_provider.release.set()
            assert response.status_code == status, response.text
            assert len(local_provider.requests) == 1
            assert local_provider.closed.wait(1), (
                "SDK left its HTTP/1.1 connection open after return"
            )
        if status == 200:
            assert store.get("test-key") is not None
        else:
            assert store.get("test-key") is None


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("terminal", [False, True])
def test_wire_validation_retry_and_failed_key_recovery(
    local_provider, tmp_path, provider, terminal
):
    store = SqliteIdempotencyStore(str(tmp_path / "idem.sqlite"))
    local_provider.steps.extend(["invalid", "invalid" if terminal else "valid"])
    with TestClient(create_app(idempotency_store=store), headers=AUTH) as client:
        response = post(client, provider)
        assert response.status_code == (422 if terminal else 200), response.text
        body = response.json()
        meta = body if terminal else body["meta"]
        assert meta["attempts"] == 2
        single_cost = 0.000045 if provider == "openai" else 0.00105
        assert meta["cost_usd"] == pytest.approx(2 * single_cost)
        retry = local_provider.requests[1]
        prompt = retry["input"] if provider == "openai" else retry["messages"][0]["content"]
        assert "Your previous response was:" in prompt
        assert "999" in prompt
        assert "value_error" in prompt
        if terminal:
            assert len(body["trail"]) == 2
            assert store.get("test-key") is None
            assert post(client, provider).status_code == 200
            assert len(local_provider.requests) == 3
        replay = post(client, provider)
        assert replay.status_code == 200
        assert replay.json()["meta"]["replayed"] is True
        assert len(local_provider.requests) == (3 if terminal else 2)


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("step, status", [("error", 502), ("timeout", 504), ("refusal", 502)])
def test_wire_provider_failure_does_not_poison_key(
    local_provider, tmp_path, provider, step, status
):
    store = SqliteIdempotencyStore(str(tmp_path / "idem.sqlite"))
    local_provider.steps.append(step)
    with TestClient(create_app(idempotency_store=store), headers=AUTH) as client:
        response = post(client, provider)
        local_provider.release.set()
        assert response.status_code == status
        assert response.json()["error"] == (
            "provider_timeout" if status == 504 else "provider_error"
        )
        assert store.get("test-key") is None
        assert post(client, provider).status_code == 200
        assert len(local_provider.requests) == 2
        assert post(client, provider).json()["meta"]["replayed"] is True
        assert len(local_provider.requests) == 2


def test_wire_cancelled_openai_response_is_retryable(local_provider, tmp_path):
    store = SqliteIdempotencyStore(str(tmp_path / "idem.sqlite"))
    local_provider.steps.append("cancelled")
    with TestClient(create_app(idempotency_store=store), headers=AUTH) as client:
        failed = post(client)
        assert failed.status_code == 502
        assert failed.json()["error"] == "provider_error"
        assert store.get("test-key") is None
        assert post(client).status_code == 200
        assert post(client).json()["meta"]["replayed"] is True
        assert len(local_provider.requests) == 2


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_wire_replay_survives_reopen_and_canonical_payload(local_provider, tmp_path, provider):
    path = str(tmp_path / "idem.sqlite")
    first_store = SqliteIdempotencyStore(path)
    with TestClient(create_app(idempotency_store=first_store), headers=AUTH) as client:
        original = post(client, provider)
        assert original.status_code == 200
        assert original.json()["meta"]["replayed"] is False
    reopened = SqliteIdempotencyStore(path)
    with TestClient(create_app(idempotency_store=reopened), headers=AUTH) as client:
        replay = post(client, provider, content_format="text", schema_version="v1")
        assert replay.status_code == 200
        assert replay.json()["meta"]["replayed"] is True
        assert replay.json()["data"] == original.json()["data"]
        assert replay.headers["X-Idempotency-Store"] == first_store.store_id == reopened.store_id
        conflict = post(client, provider, content="Different synthetic invoice")
        assert conflict.status_code == 409
        assert conflict.json()["error"] == "idempotency_conflict"
    assert len(local_provider.requests) == 1


def synthetic_pdf(*, text="Synthetic invoice"):
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        if text:
            page.insert_text((72, 72), text)
        return base64.b64encode(pdf.tobytes()).decode()


def test_real_pdf_text_reaches_wire_provider(local_provider, tmp_path):
    store = SqliteIdempotencyStore(str(tmp_path / "idem.sqlite"))
    with TestClient(create_app(idempotency_store=store), headers=AUTH) as client:
        response = post(client, content_format="pdf_base64", content=synthetic_pdf())
        assert response.status_code == 200
    assert len(local_provider.requests) == 1
    assert "Synthetic invoice" in local_provider.requests[0]["input"]


@pytest.mark.parametrize("kind", ["base64", "corrupt_pdf", "blank_pdf", "text_limit", "pdf_limit"])
def test_invalid_content_never_reaches_provider_or_poisons_key(local_provider, tmp_path, kind):
    store = SqliteIdempotencyStore(str(tmp_path / "idem.sqlite"))
    content_format = "pdf_base64"
    if kind == "base64":
        content = "!!!"
    elif kind == "corrupt_pdf":
        content = base64.b64encode(b"%PDF-1.7\ninvalid synthetic file").decode()
    elif kind == "blank_pdf":
        content = synthetic_pdf(text="")
    elif kind == "text_limit":
        content_format = "text"
        content = "x" * (4 * 1024 * 1024 + 1)
    else:
        content = base64.b64encode(b"x" * (10 * 1024 * 1024 + 1)).decode()
    with TestClient(create_app(idempotency_store=store), headers=AUTH) as client:
        rejected = post(client, content_format=content_format, content=content)
        assert rejected.status_code == 422
        assert rejected.json()["error"] == "validation_failed"
        assert local_provider.requests == []
        assert store.get("test-key") is None
        assert post(client).status_code == 200
        assert len(local_provider.requests) == 1


def test_auth_and_body_caps_precede_provider_work(local_provider, tmp_path, monkeypatch):
    store = SqliteIdempotencyStore(str(tmp_path / "idem.sqlite"))
    monkeypatch.setenv("EXTRACT_MAX_BODY_BYTES", "256")
    with TestClient(create_app(idempotency_store=store)) as client:
        unauthorized = client.post("/v1/extract", content=b"x" * 257)
        assert unauthorized.status_code == 401
        assert unauthorized.json()["error"] == "unauthorized"
        oversized = client.post("/v1/extract", content=b"x" * 257, headers=AUTH)
        assert oversized.status_code == 422
        assert "256-byte limit" in oversized.json()["detail"]
        malformed = client.post("/v1/extract", content=b"{", headers=AUTH)
        assert malformed.status_code == 422
        assert malformed.json()["error"] == "validation_failed"
    assert local_provider.requests == []
    assert store.get("test-key") is None


def test_parallel_distinct_keys_persist_and_replay_independently(
    local_provider, tmp_path, monkeypatch
):
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_S", "4")
    store = SqliteIdempotencyStore(str(tmp_path / "idem.sqlite"))
    local_provider.steps.extend(["barrier", "barrier"])
    with TestClient(create_app(idempotency_store=store), headers=AUTH) as client:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(post, client, key="first")
            second = pool.submit(post, client, key="second", content="Second synthetic invoice")
            assert first.result(timeout=5).status_code == 200
            assert second.result(timeout=5).status_code == 200
        assert len(local_provider.requests) == 2
        assert store.get("first") is not None
        assert store.get("second") is not None
        assert post(client, key="first").json()["meta"]["replayed"] is True
        assert post(client, key="second", content="Second synthetic invoice").json()["meta"][
            "replayed"
        ]
        assert len(local_provider.requests) == 2


def test_client_disconnect_during_sync_provider_call_still_commits_success(
    local_provider, tmp_path, monkeypatch
):
    # A dropped frontend connection does not cancel the synchronous extraction thread.
    # The eventual success must remain replayable, avoiding another paid call on retry.
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_S", "3")
    store = SqliteIdempotencyStore(str(tmp_path / "idem.sqlite"))
    app = create_app(idempotency_store=store)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, lifespan="off", ws="none", log_config=None, access_log=False)
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 3
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        local_provider.steps.append("hold")
        body = json.dumps(
            {"doc_type": "invoice", "content": "Synthetic invoice", "provider": "openai"}
        )
        request = (
            "POST /v1/extract HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            f"Authorization: {AUTH['Authorization']}\r\n"
            "Idempotency-Key: test-key\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n\r\n{body}"
        )
        with socket.create_connection(("127.0.0.1", port), timeout=3) as connection:
            connection.sendall(request.encode())
            assert local_provider.entered.wait(2)
            # Closing here simulates a caller leaving before its provider has answered.
        local_provider.release.set()
        deadline = time.monotonic() + 3
        while store.get("test-key") is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert store.get("test-key") is not None
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", headers=AUTH, timeout=3) as client:
            replay = post(client)
            assert replay.status_code == 200
            assert replay.json()["meta"]["replayed"] is True
        assert len(local_provider.requests) == 1
    finally:
        local_provider.release.set()
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        assert not thread.is_alive()
