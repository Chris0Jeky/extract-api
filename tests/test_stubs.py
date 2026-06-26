"""M0 stubs fail loudly (NotImplementedError) until their task lands."""

import pytest

from api.idempotency import SqliteIdempotencyStore, StoredResponse, payload_hash
from harness.run_accuracy import run_accuracy


def test_payload_hash_is_real_and_stable():
    assert payload_hash(b"abc") == payload_hash(b"abc")
    assert payload_hash(b"abc") != payload_hash(b"abd")
    assert len(payload_hash(b"abc")) == 64


def test_idempotency_store_methods_are_stubbed():
    store = SqliteIdempotencyStore("ignored.sqlite")
    with pytest.raises(NotImplementedError):
        store.get("k")
    with pytest.raises(NotImplementedError):
        store.put("k", StoredResponse("h", "{}", 200, 0.0))
    with pytest.raises(NotImplementedError):
        store.sweep()


def test_accuracy_stub():
    with pytest.raises(NotImplementedError):
        run_accuracy("invoice", "openai")
