"""The extract admission cap: queued extracts wait before their bodies are read, and the
health probes never wait behind them."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient

from api.main import ExtractAdmission, create_app
from llm.client import FixtureClient


@pytest.mark.parametrize("raw, expected", [(None, 4), ("1", 1), ("7", 7), ("40", 40)])
def test_admission_cap_comes_from_env(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("EXTRACT_MAX_CONCURRENCY", raising=False)
    else:
        monkeypatch.setenv("EXTRACT_MAX_CONCURRENCY", raw)

    (gate,) = [m for m in create_app().user_middleware if m.cls is ExtractAdmission]
    assert gate.kwargs == {"limit": expected}


@pytest.mark.parametrize("raw", ["", "invalid", "0", "-1", "1.5", "1_0", " 4", "٤"])
def test_invalid_concurrency_fails_at_startup(monkeypatch, raw):
    monkeypatch.setenv("EXTRACT_MAX_CONCURRENCY", raw)
    with pytest.raises(ValueError, match="EXTRACT_MAX_CONCURRENCY must be a positive integer"):
        create_app()


def test_a_queued_extract_is_not_admitted_until_a_slot_frees():
    # The inner app is the only reader of the request body, so "not invoked" means "body not
    # read": a queued request holds a connection, not its payload.
    started: list[str] = []
    release = anyio.Event()

    async def inner(scope, receive, send):
        started.append(scope["path"])
        if scope["path"] == "/v1/extract":
            await release.wait()

    gate = ExtractAdmission(inner, limit=1)
    http = {"type": "http"}

    async def scenario():
        async with anyio.create_task_group() as tg:
            tg.start_soon(gate, {**http, "path": "/v1/extract"}, None, None)
            tg.start_soon(gate, {**http, "path": "/v1/extract"}, None, None)
            await anyio.wait_all_tasks_blocked()
            assert started == ["/v1/extract"]
            await gate({**http, "path": "/readyz"}, None, None)  # never gated
            assert started == ["/v1/extract", "/readyz"]
            release.set()
        assert started == ["/v1/extract", "/readyz", "/v1/extract"]

    anyio.run(scenario)


def test_saturated_pool_queues_extracts_and_health_stays_responsive(monkeypatch):
    monkeypatch.setenv("EXTRACT_MAX_CONCURRENCY", "1")
    fixture = json.loads(Path("fixtures/invoices/invoice_0001.json").read_text(encoding="utf-8"))
    entered = threading.Event()
    release = threading.Event()
    active = 0
    max_active = 0
    calls = 0
    lock = threading.Lock()

    class SlowFixture(FixtureClient):
        def complete(self, **kwargs):
            nonlocal active, max_active, calls
            with lock:
                active += 1
                calls += 1
                max_active = max(active, max_active)
            entered.set()
            try:
                assert release.wait(5), "test did not release the slow fixture"
                return super().complete(**kwargs)
            finally:
                with lock:
                    active -= 1

    fixture_client = SlowFixture(json.dumps(fixture["expected"]), latency_ms=100)
    monkeypatch.setattr("api.main.get_client", lambda provider: fixture_client)

    app = create_app()
    gate = app.middleware_stack = app.build_middleware_stack()
    while not isinstance(gate, ExtractAdmission):
        gate = gate.app

    async def waiting():
        return gate.limiter.statistics().tasks_waiting

    with TestClient(app) as client, ThreadPoolExecutor(max_workers=3) as pool:
        body = {"doc_type": "invoice", "content": fixture["content"]}
        first = pool.submit(client.post, "/v1/extract", json=body)
        try:
            assert entered.wait(2)
            second = pool.submit(client.post, "/v1/extract", json=body)
            deadline = time.monotonic() + 2
            while client.portal.call(waiting) == 0 and time.monotonic() < deadline:
                time.sleep(0.01)
            assert client.portal.call(waiting) == 1
            health = pool.submit(client.get, "/healthz").result(timeout=0.5)
            assert health.status_code == 200
            assert not first.done() and not second.done()
        finally:
            release.set()
        assert first.result(timeout=2).status_code == 200
        assert second.result(timeout=2).status_code == 200
    assert calls == 2
    assert max_active == 1
