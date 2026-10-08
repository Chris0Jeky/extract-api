"""Startup thread cap and queued sync extracts with an independent health probe."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anyio.to_thread
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from llm.client import FixtureClient


@pytest.mark.parametrize("raw, expected", [(None, 4), ("1", 1), ("7", 7), ("40", 40)])
def test_limiter_is_set_during_startup(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("EXTRACT_MAX_CONCURRENCY", raising=False)
    else:
        monkeypatch.setenv("EXTRACT_MAX_CONCURRENCY", raw)

    async def tokens():
        return anyio.to_thread.current_default_thread_limiter().total_tokens

    with TestClient(create_app()) as client:
        assert client.portal.call(tokens) == expected
        assert client.get("/healthz").status_code == 200


@pytest.mark.parametrize("raw", ["", "invalid", "0", "-1", "1.5", "1_0", " 4", "٤"])
def test_invalid_concurrency_fails_at_startup(monkeypatch, raw):
    monkeypatch.setenv("EXTRACT_MAX_CONCURRENCY", raw)
    app = create_app()
    with (
        pytest.raises(ValueError, match="EXTRACT_MAX_CONCURRENCY must be a positive integer"),
        TestClient(app),
    ):
        pytest.fail("invalid concurrency allowed startup")


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

    async def waiting():
        return anyio.to_thread.current_default_thread_limiter().statistics().tasks_waiting

    with TestClient(create_app()) as client, ThreadPoolExecutor(max_workers=3) as pool:
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
