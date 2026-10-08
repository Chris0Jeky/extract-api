"""/readyz is the platform health check (ADR 0005): ready only while the idempotency store
can commit a write, and it reports the image revision and provider mode."""

import os
import sqlite3
import stat

import pytest
from fastapi.testclient import TestClient

from api.idempotency import SqliteIdempotencyStore
from api.main import create_app


@pytest.fixture
def store(tmp_path):
    return SqliteIdempotencyStore(str(tmp_path / "ready.sqlite"))


def test_ready_with_a_writable_store(store, monkeypatch):
    monkeypatch.setenv("EXTRACT_API_REVISION", "a" * 40)
    monkeypatch.setenv("LLM_PROVIDER_MODE", "fixture")
    resp = TestClient(create_app(idempotency_store=store)).get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "revision": "a" * 40, "provider_mode": "fixture"}


def test_unset_revision_and_live_mode_are_reported_not_guessed(store, monkeypatch):
    monkeypatch.delenv("EXTRACT_API_REVISION", raising=False)
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    body = TestClient(create_app(idempotency_store=store)).get("/readyz").json()
    assert body["revision"] == "unknown"
    assert body["provider_mode"] == "live"


def test_probe_commits_one_fixed_row(store, tmp_path):
    store.probe()
    store.probe()
    with sqlite3.connect(tmp_path / "ready.sqlite") as conn:
        assert conn.execute("SELECT COUNT(*) FROM readiness_probe").fetchone() == (1,)


def test_read_only_store_is_not_ready(store, tmp_path):
    # The failure a root-owned or read-only disk produces: reads work, writes do not.
    db = tmp_path / "ready.sqlite"
    os.chmod(db, stat.S_IREAD)
    try:
        client = TestClient(create_app(idempotency_store=store), raise_server_exceptions=False)
        resp = client.get("/readyz")
    finally:
        os.chmod(db, stat.S_IREAD | stat.S_IWRITE)
    assert resp.status_code == 500
    assert resp.json()["error"] == "internal_error"
    assert "not ready" in resp.json()["detail"]


def test_unopenable_store_path_is_not_ready(tmp_path, monkeypatch):
    # The default store is built lazily from env; a path whose directory does not exist (a
    # missing disk mount) must fail readiness, not crash the app at import.
    monkeypatch.setenv("IDEMPOTENCY_DB_PATH", str(tmp_path / "no-such-dir" / "i.sqlite"))
    client = TestClient(create_app(), raise_server_exceptions=False)
    assert client.get("/healthz").status_code == 200
    resp = client.get("/readyz")
    assert resp.status_code == 500
    assert resp.json()["error"] == "internal_error"
