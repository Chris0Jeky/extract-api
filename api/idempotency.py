"""Idempotency: Idempotency-Key + sha256(payload) stored with the response.

Semantics (ADR 0004, SQLite store for v1):
- same key + same payload hash -> replay the stored response, no model call,
  meta.replayed = true.
- same key + different payload hash -> idempotency_conflict (409).
- TTL 24h.

The store is a thin interface so the gateway-era Postgres swap is one adapter.
`payload_hash` and the SQLite store are real (T11); the endpoint wiring (replay /
409 / replayed:true) lands in T12.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from typing import Protocol


def payload_hash(body: bytes) -> str:
    """Stable sha256 of the raw request body."""
    return hashlib.sha256(body).hexdigest()


@dataclass(frozen=True)
class StoredResponse:
    payload_sha256: str
    response_json: str
    status_code: int
    created_at_epoch: float


class IdempotencyStore(Protocol):
    def get(self, key: str) -> StoredResponse | None: ...

    def put(self, key: str, stored: StoredResponse) -> None: ...

    def sweep(self) -> int:
        """Delete entries older than the TTL; return how many were removed."""
        ...


class SqliteIdempotencyStore:
    """File-backed idempotency store (ADR 0004).

    One connection is opened per operation (so each request thread gets its own and
    sqlite's default same-thread check is satisfied), with a busy timeout so brief
    write contention waits rather than failing. Entries older than the TTL are treated
    as absent on read and removed; `sweep` reclaims them in bulk.
    """

    def __init__(self, db_path: str, ttl_hours: int = 24, *, busy_timeout_s: float = 5.0) -> None:
        self._db_path = db_path
        self._ttl_hours = ttl_hours
        self._busy_timeout_s = busy_timeout_s
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=self._busy_timeout_s)

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            # WAL lets readers proceed alongside a single writer under the request
            # threadpool (ADR 0004's concurrency rationale). It is a persistent property of
            # the db file, so enabling it once at init suffices; both journal modes are
            # ACID, so this is best-effort (a filesystem that rejects WAL still yields a
            # correct store, just with the default rollback journal).
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS idempotency ("
                " key TEXT PRIMARY KEY,"
                " payload_sha256 TEXT NOT NULL,"
                " response_json TEXT NOT NULL,"
                " status_code INTEGER NOT NULL,"
                " created_at_epoch REAL NOT NULL)"
            )
            conn.commit()

    def get(self, key: str) -> StoredResponse | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT payload_sha256, response_json, status_code, created_at_epoch"
                " FROM idempotency WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        stored = StoredResponse(
            payload_sha256=str(row[0]),
            response_json=str(row[1]),
            status_code=int(row[2]),
            created_at_epoch=float(row[3]),
        )
        if self._is_expired(stored):
            # An expired hit is no hit: drop it so a stale response is never replayed. Scope
            # the delete to the exact row we read (by timestamp), so if a fresh put replaced
            # it between this SELECT and the DELETE, the fresh row is preserved.
            self._delete_expired(key, stored.created_at_epoch)
            return None
        return stored

    def put(self, key: str, stored: StoredResponse) -> None:
        # First-writer-wins (INSERT OR IGNORE): once a response is stored for a key it is the
        # canonical one and a later put (e.g. a thread race where two callers both miss
        # get()) is a no-op, not an overwrite. This keeps the stored response stable, which
        # is what replay and the same-key-different-hash 409 (T12) rely on.
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO idempotency"
                " (key, payload_sha256, response_json, status_code, created_at_epoch)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    key,
                    stored.payload_sha256,
                    stored.response_json,
                    stored.status_code,
                    stored.created_at_epoch,
                ),
            )
            conn.commit()

    def sweep(self) -> int:
        cutoff = time.time() - self._ttl_seconds()
        with closing(self._connect()) as conn:
            cur = conn.execute("DELETE FROM idempotency WHERE created_at_epoch < ?", (cutoff,))
            conn.commit()
            return cur.rowcount

    def _ttl_seconds(self) -> float:
        return self._ttl_hours * 3600.0

    def _is_expired(self, stored: StoredResponse) -> bool:
        return (time.time() - stored.created_at_epoch) > self._ttl_seconds()

    def _delete_expired(self, key: str, created_at_epoch: float) -> None:
        # Delete only the exact (key, created_at) row we read as expired. The stored epoch
        # is the same double we read back, so the equality match is exact; a fresher row
        # for the same key has a different epoch and is left untouched.
        with closing(self._connect()) as conn:
            conn.execute(
                "DELETE FROM idempotency WHERE key = ? AND created_at_epoch = ?",
                (key, created_at_epoch),
            )
            conn.commit()
