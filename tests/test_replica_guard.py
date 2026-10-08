"""Single-replica safety (ADR 0004): the store has a stable identity that every keyed response
and /readyz expose, and a deployment can require the store to sit on a persistent mount."""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import idempotency
from api.idempotency import SqliteIdempotencyStore
from api.main import create_app

_FIXTURE = json.loads(
    (Path(__file__).resolve().parent.parent / "fixtures/invoices/invoice_0001.json").read_text(
        encoding="utf-8"
    )
)
_PAYLOAD = {
    "doc_type": _FIXTURE["doc_type"],
    "schema_version": _FIXTURE["schema_version"],
    "content": _FIXTURE["content"],
    "provider": "openai",
}


@pytest.fixture(autouse=True)
def _fixture_mode(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_MODE", "fixture")
    monkeypatch.setenv("FIXTURE_CANNED_TEXT", json.dumps(_FIXTURE["expected"]))


def test_store_id_survives_reopening_the_same_file(tmp_path):
    path = str(tmp_path / "i.sqlite")
    first = SqliteIdempotencyStore(path).store_id
    assert len(first) == 32
    assert SqliteIdempotencyStore(path).store_id == first
    assert SqliteIdempotencyStore(str(tmp_path / "other.sqlite")).store_id != first


def test_readyz_and_keyed_responses_name_the_store(tmp_path):
    store = SqliteIdempotencyStore(str(tmp_path / "i.sqlite"))
    client = TestClient(create_app(idempotency_store=store))
    assert client.get("/readyz").json()["idempotency_store_id"] == store.store_id
    keyed = client.post("/v1/extract", json=_PAYLOAD, headers={"Idempotency-Key": "k1"})
    assert keyed.status_code == 200
    assert keyed.headers["X-Idempotency-Store"] == store.store_id
    unkeyed = client.post("/v1/extract", json=_PAYLOAD)
    assert "X-Idempotency-Store" not in unkeyed.headers


def test_a_second_store_is_visible_to_the_client(tmp_path):
    # The failure the guard exists to expose: a retry that reaches another replica's store
    # is not replayed (the model runs again). The header is how a client can tell.
    a = TestClient(create_app(idempotency_store=SqliteIdempotencyStore(str(tmp_path / "a.db"))))
    b = TestClient(create_app(idempotency_store=SqliteIdempotencyStore(str(tmp_path / "b.db"))))
    first = a.post("/v1/extract", json=_PAYLOAD, headers={"Idempotency-Key": "same"})
    retry = b.post("/v1/extract", json=_PAYLOAD, headers={"Idempotency-Key": "same"})
    assert retry.json()["meta"]["replayed"] is False
    assert retry.headers["X-Idempotency-Store"] != first.headers["X-Idempotency-Store"]


def test_root_filesystem_detection():
    assert idempotency._on_root_filesystem(os.path.join(os.path.abspath(os.sep), "i.sqlite"))


def test_store_off_a_persistent_mount_is_not_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(idempotency, "_on_root_filesystem", lambda _path: True)
    monkeypatch.setenv("IDEMPOTENCY_DB_PATH", str(tmp_path / "i.sqlite"))
    monkeypatch.setenv("IDEMPOTENCY_REQUIRE_PERSISTENT_MOUNT", "1")
    resp = TestClient(create_app(), raise_server_exceptions=False).get("/readyz")
    assert resp.status_code == 500
    assert resp.json()["error"] == "internal_error"
    assert "persistent mount" in resp.json()["detail"]


def test_store_on_a_persistent_mount_is_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(idempotency, "_on_root_filesystem", lambda _path: False)
    monkeypatch.setenv("IDEMPOTENCY_DB_PATH", str(tmp_path / "i.sqlite"))
    monkeypatch.setenv("IDEMPOTENCY_REQUIRE_PERSISTENT_MOUNT", "1")
    assert TestClient(create_app()).get("/readyz").status_code == 200


def test_the_requirement_is_off_unless_asked_for(tmp_path, monkeypatch):
    # Local development keeps the store in the working directory, on the root device.
    monkeypatch.setattr(idempotency, "_on_root_filesystem", lambda _path: True)
    monkeypatch.setenv("IDEMPOTENCY_DB_PATH", str(tmp_path / "i.sqlite"))
    monkeypatch.delenv("IDEMPOTENCY_REQUIRE_PERSISTENT_MOUNT", raising=False)
    assert TestClient(create_app()).get("/readyz").status_code == 200


def test_a_malformed_requirement_fails_loud(tmp_path, monkeypatch):
    monkeypatch.setenv("IDEMPOTENCY_DB_PATH", str(tmp_path / "i.sqlite"))
    monkeypatch.setenv("IDEMPOTENCY_REQUIRE_PERSISTENT_MOUNT", "yes")
    resp = TestClient(create_app(), raise_server_exceptions=False).get("/readyz")
    assert resp.status_code == 500
