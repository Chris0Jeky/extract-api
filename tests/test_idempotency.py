"""SqliteIdempotencyStore: payload hashing + put/get/sweep with TTL (T11).

Storage only; the endpoint wiring (replay / 409 / replayed:true) is exercised in T12.
Each test uses a fresh tmp_path db file, so they are isolated and offline.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing

from api.idempotency import SqliteIdempotencyStore, StoredResponse, payload_hash


def _stored(*, sha="sha-abc", body='{"x":1}', status=200, created_at=None):
    return StoredResponse(
        payload_sha256=sha,
        response_json=body,
        status_code=status,
        created_at_epoch=time.time() if created_at is None else created_at,
    )


def _store(tmp_path, ttl_hours=24):
    return SqliteIdempotencyStore(str(tmp_path / "idem.sqlite"), ttl_hours=ttl_hours)


def test_uses_wal_journal_mode(tmp_path):
    # ADR 0004: WAL handles the low-concurrency load (readers alongside one writer). WAL is
    # persistent, so a fresh connection to the same file reports it.
    _store(tmp_path)
    with closing(sqlite3.connect(str(tmp_path / "idem.sqlite"))) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"


def test_payload_hash_is_stable_and_distinguishing():
    assert payload_hash(b"hello") == payload_hash(b"hello")
    assert payload_hash(b"hello") != payload_hash(b"world")
    assert len(payload_hash(b"hello")) == 64  # sha256 hex


def test_put_then_get_roundtrips(tmp_path):
    store = _store(tmp_path)
    stored = _stored()
    store.put("k1", stored)
    assert store.get("k1") == stored


def test_get_missing_key_returns_none(tmp_path):
    assert _store(tmp_path).get("nope") is None


def test_get_drops_and_hides_expired_entry(tmp_path):
    store = _store(tmp_path, ttl_hours=24)
    store.put("old", _stored(created_at=time.time() - 25 * 3600))  # older than 24h
    assert store.get("old") is None
    # The expired entry was removed on read, so a later sweep finds nothing.
    assert store.sweep() == 0


def test_get_keeps_fresh_entry_within_ttl(tmp_path):
    store = _store(tmp_path, ttl_hours=24)
    fresh = _stored(created_at=time.time() - 3600)  # 1h old, within 24h
    store.put("new", fresh)
    assert store.get("new") == fresh


def test_sweep_removes_only_expired(tmp_path):
    store = _store(tmp_path, ttl_hours=24)
    store.put("fresh", _stored(created_at=time.time() - 3600))
    store.put("stale1", _stored(created_at=time.time() - 25 * 3600))
    store.put("stale2", _stored(created_at=time.time() - 100 * 3600))
    assert store.sweep() == 2
    assert store.get("fresh") is not None
    assert store.get("stale1") is None


def test_put_is_first_writer_wins(tmp_path):
    # Once a key is stored it is canonical; a later put for the same key is a no-op, so the
    # stored response stays stable (replay + the same-key-different-hash 409 depend on this).
    store = _store(tmp_path)
    store.put("k", _stored(body='{"v":1}'))
    store.put("k", _stored(body='{"v":2}'))
    got = store.get("k")
    assert got is not None
    assert got.response_json == '{"v":1}'


def test_expired_delete_is_scoped_to_the_read_row(tmp_path):
    # The expiry delete on read must not clobber a fresh row that replaced the expired one
    # in the gap. A stale delete qualified by the OLD timestamp must leave the fresh row.
    store = _store(tmp_path, ttl_hours=24)
    old = time.time() - 25 * 3600
    store.put("k", _stored(created_at=old))  # expired row
    assert store.get("k") is None  # reads expired -> deletes only the old-timestamp row
    store.put("k", _stored(body='{"fresh":true}'))  # a fresh row now lands for the same key
    store._delete_expired("k", old)  # a late, stale expiry-delete for the OLD row
    got = store.get("k")
    assert got is not None
    assert got.response_json == '{"fresh":true}'  # the fresh row survived


def test_persists_across_store_instances(tmp_path):
    # File-backed, not in-memory: a reopened store on the same path sees prior writes.
    path = str(tmp_path / "idem.sqlite")
    SqliteIdempotencyStore(path).put("k", _stored(body='{"persisted":true}'))
    got = SqliteIdempotencyStore(path).get("k")
    assert got is not None
    assert got.response_json == '{"persisted":true}'
