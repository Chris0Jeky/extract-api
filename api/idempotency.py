"""Idempotency: Idempotency-Key + sha256(payload) stored with the response.

Semantics (ADR 0004, SQLite store for v1):
- same key + same payload hash -> replay the stored response, no model call,
  meta.replayed = true.
- same key + different payload hash -> idempotency_conflict (409).
- TTL 24h.

The store is a thin interface so the gateway-era Postgres swap is one adapter.
`payload_hash` is real now; the storage methods land in T11.
"""

from __future__ import annotations

import hashlib
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
    """File-backed idempotency store. Methods land in T11."""

    def __init__(self, db_path: str, ttl_hours: int = 24) -> None:
        self._db_path = db_path
        self._ttl_hours = ttl_hours

    def get(self, key: str) -> StoredResponse | None:
        raise NotImplementedError("SQLite idempotency get lands in T11")

    def put(self, key: str, stored: StoredResponse) -> None:
        raise NotImplementedError("SQLite idempotency put lands in T11")

    def sweep(self) -> int:
        raise NotImplementedError("SQLite idempotency sweep lands in T11")
