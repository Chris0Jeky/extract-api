"""M0 stubs fail loudly (NotImplementedError) until their task lands.

The accuracy harness is implemented (T16; see test_scoring.py + test_run_accuracy.py);
the idempotency store remains a stub until T11.
"""

import pytest

from api.idempotency import SqliteIdempotencyStore, StoredResponse, payload_hash


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
