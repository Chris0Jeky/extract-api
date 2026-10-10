"""Caller authentication for POST /v1/extract.

Owner decision `extract-api-caller-auth`, answered (a) on 2026-10-10 (agent-hq PR 356): callers
send `Authorization: Bearer <key>`; the service stores only SHA-256 hashes of the keys, in the
secret `EXTRACT_API_KEY_SHA256S` (comma separated hex digests); two or more keys can be valid at
once, so a rotation never needs downtime; a service with no hashes refuses to serve extractions;
/healthz and /readyz stay open.

The check is an ASGI middleware, not a route dependency, for two reasons. It runs before the
body is read, so an unauthenticated caller costs one header parse (a dependency would let
FastAPI read and validate the body first, answering 422 where it should answer 401). And it sits
outside `ExtractAdmission`, so a rejected caller never holds one of the scarce extraction slots.

Neither a presented token nor any hash is ever logged or placed in an error message.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re

from starlette.types import ASGIApp, Receive, Scope, Send

from api.errors import ErrorCode, error_response
from api.observability import note

logger = logging.getLogger("extract.api")

ENV_VAR = "EXTRACT_API_KEY_SHA256S"
GUARDED_PATH = "/v1/extract"
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def key_hashes_from_env() -> tuple[bytes, ...]:
    """Parse EXTRACT_API_KEY_SHA256S into raw 32-byte digests; empty means no key is valid.

    A malformed entry fails startup so a typo cannot silently drop a key, and the message never
    echoes the entry: an operator may have pasted a plaintext key where a hash belongs.
    """
    digests: dict[bytes, None] = {}
    for position, entry in enumerate(os.environ.get(ENV_VAR, "").split(","), start=1):
        entry = entry.strip().lower()
        if not entry:
            continue
        if not _SHA256_HEX.fullmatch(entry):
            raise ValueError(
                f"{ENV_VAR} entry {position} is not a 64-character hex SHA-256 digest"
                " (store the hash of the key, never the key)"
            )
        digests[bytes.fromhex(entry)] = None
    return tuple(digests)


def _bearer_token(scope: Scope) -> str | None:
    """The token of a well-formed `Authorization: Bearer <token>` header, else None."""
    for name, value in scope["headers"]:
        if name == b"authorization":
            header: str = value.decode("latin-1")
            scheme, _, token = header.partition(" ")
            # Scheme names are case-insensitive (RFC 9110). A token has no spaces, so
            # trailing words make the header malformed rather than a different token.
            if scheme.lower() == "bearer" and token and " " not in token:
                return token
            return None
    return None


def _matches(token: str, hashes: tuple[bytes, ...]) -> bool:
    presented = hashlib.sha256(token.encode("utf-8", "surrogatepass")).digest()
    # Every hash is compared, even after a match, so timing does not reveal which key matched
    # or how many are configured.
    matched = False
    for stored in hashes:
        matched |= hmac.compare_digest(presented, stored)
    return matched


class CallerAuth:
    """Require a valid bearer key on /v1/extract; every other route passes through."""

    def __init__(self, app: ASGIApp, *, key_hashes: tuple[bytes, ...]) -> None:
        self.app = app
        self.key_hashes = key_hashes
        if not key_hashes:
            logger.error(
                "%s holds no key hash: /v1/extract refuses every request until one is set",
                ENV_VAR,
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] != GUARDED_PATH:
            await self.app(scope, receive, send)
            return
        note(route=GUARDED_PATH)  # the access line would otherwise say "unmatched"
        if not self.key_hashes:
            # Fail closed. A service fault, not the caller's credentials, so it is the 500
            # internal_error that /readyz uses for the same class of fault: a 401 would send
            # callers hunting for a key problem, and would hide the outage from 5xx alerting.
            response = error_response(
                ErrorCode.internal_error,
                {
                    "error": ErrorCode.internal_error.value,
                    "detail": "the service is not configured to serve extractions",
                },
            )
        else:
            token = _bearer_token(scope)
            if token is not None and _matches(token, self.key_hashes):
                await self.app(scope, receive, send)
                return
            # One message for missing, malformed and wrong: nothing to tell them apart by.
            response = error_response(
                ErrorCode.unauthorized,
                {
                    "error": ErrorCode.unauthorized.value,
                    "detail": "a valid API key is required (Authorization: Bearer <key>)",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        await response(scope, receive, send)
