"""Structured JSON logs, request ids and one summary line per request.

The rule this module enforces: logs describe a request, they never carry it. No document
text, PDF bytes, model output, Idempotency-Key value or Authorization header is ever
written. Three mechanisms keep a careless future log call from leaking:

* the JSON formatter emits only an explicit allowlist of structured fields from `extra=`;
* exception messages are dropped (type + stack frames only), because a message can echo
  the value that failed (a pydantic error repeats its input);
* the access line is assembled from facts the endpoint notes explicitly (`note*`), never
  from the request or response body.

`RequestContextMiddleware` is pure ASGI (not BaseHTTPMiddleware, which breaks contextvars
and buffers responses). It binds the request id and a per-request facts dict in
contextvars; `note()` fills the dict from the sync endpoint, which Starlette runs in a
threadpool with the context copied (the dict itself is shared by reference).
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import sys
import time
import traceback
import uuid
from collections.abc import MutableMapping
from datetime import UTC, datetime
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.models import ExtractMeta, ExtractRequest

REQUEST_ID_HEADER = "X-Request-ID"
# Anything else (newline, spaces, over 128 chars) is replaced: the id is echoed in a header
# and written into every log line, so an unvalidated value is a log-injection vector.
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")
# Scope key so the 500 handler (which runs outside the middleware, in ServerErrorMiddleware)
# can still echo the id.
SCOPE_KEY = "extract.request_id"

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "extract_request_id", default=None
)
_facts: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "extract_request_facts", default=None
)

# Structured fields a log call may attach via `extra=`. Everything else is dropped.
ALLOWED_FIELDS = (
    "request_id",
    "method",
    "route",
    "status",
    "duration_ms",
    "doc_type",
    "schema_version",
    "provider_requested",
    "provider",
    "model",
    "attempts",
    "retry_class",
    "result",
    "cost_usd",
    "replayed",
    "idempotency_keyed",
    "content_kind",
    "content_bytes",
    "attempt",
    "retry_kinds",
)
_MAX_STR = 256
_ACCESS = logging.getLogger("extract.access")


def _scalar(value: Any) -> Any:
    """Bound an allowlisted value: scalars pass, strings are capped, lists of scalars pass."""
    if isinstance(value, str):
        return value[:_MAX_STR]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [_scalar(v) for v in value[:32]]
    return str(value)[:_MAX_STR]


def _redacted_exc(exc_info: Any) -> tuple[str, list[str]]:
    """Exception type and stack frames only: the message is deliberately omitted."""
    frames = [f"{f.filename}:{f.lineno} in {f.name}" for f in traceback.extract_tb(exc_info[2])]
    return exc_info[0].__name__, frames[-12:]


class TextFormatter(logging.Formatter):
    """LOG_FORMAT=text: the plain line, with exceptions redacted exactly like the JSON one."""

    def format(self, record: logging.LogRecord) -> str:
        # Hide the exception from the base class (it prints the message and caches it in
        # record.exc_text, which another handler may already have filled), then append ours.
        exc_info, exc_text = record.exc_info, record.exc_text
        record.exc_info = record.exc_text = None
        try:
            line = super().format(record)
        finally:
            record.exc_info, record.exc_text = exc_info, exc_text
        if exc_info and exc_info[0] is not None:
            exc_type, frames = _redacted_exc(exc_info)
            line += "\n" + exc_type + "".join(f"\n  {f}" for f in frames)
        return line


class JsonFormatter(logging.Formatter):
    """One JSON object per line: ts, level, logger, msg, request_id, allowlisted extras."""

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = getattr(record, "request_id", None) or _request_id.get()
        if rid:
            out["request_id"] = rid
        for name in ALLOWED_FIELDS:
            if name != "request_id" and hasattr(record, name):
                out[name] = _scalar(getattr(record, name))
        if record.exc_info and record.exc_info[0] is not None:
            out["exc_type"], out["stack"] = _redacted_exc(record.exc_info)
        return json.dumps(out, separators=(",", ":"), ensure_ascii=True)


class _StdoutHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Writes to whatever sys.stdout is at emit time (so pytest/capsys swaps are honoured)."""

    def __init__(self) -> None:
        logging.Handler.__init__(self)

    @property
    def stream(self) -> Any:
        return sys.stdout


_MARK = "_extract_observability"
# Third-party loggers whose DEBUG output includes request bodies (the OpenAI SDK logs
# request options, i.e. the prompt, at DEBUG): never below WARNING.
_QUIET = ("openai", "anthropic", "httpx", "httpcore")


def logging_configured() -> bool:
    return any(getattr(h, _MARK, False) for h in logging.getLogger().handlers)


def configure_logging() -> None:
    """JSON (default) or text (LOG_FORMAT=text, local dev) to stdout; LOG_LEVEL, default INFO.

    Idempotent: it adds at most one handler, marked, and never removes or replaces the
    others (pytest's caplog handlers live on the root logger). Invalid values fail loud.
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    level = logging.getLevelNamesMapping().get(level_name)
    if level is None or level == logging.NOTSET:
        raise ValueError(f"invalid LOG_LEVEL {level_name!r}; use DEBUG, INFO, WARNING, ERROR")
    fmt = os.environ.get("LOG_FORMAT", "json").strip().lower()
    if fmt not in {"json", "text"}:
        raise ValueError(f"invalid LOG_FORMAT {fmt!r}; use json or text")

    root = logging.getLogger()
    handler = next((h for h in root.handlers if getattr(h, _MARK, False)), None)
    if handler is None:
        handler = _StdoutHandler()
        setattr(handler, _MARK, True)
        root.addHandler(handler)
    handler.setFormatter(
        JsonFormatter()
        if fmt == "json"
        else TextFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.setLevel(level)
    # uvicorn's default config gives the PARENT `uvicorn` logger its own stderr handler with
    # propagate False (uvicorn.error just propagates into it), so clearing only uvicorn.error
    # leaves "Exception in ASGI application" tracebacks, message included, on plain stderr.
    # Route both through ours. Its access log prints the raw path and query: keep it off even
    # if --no-access-log is forgotten (uvicorn applies its config before the app is imported).
    for name in ("uvicorn", "uvicorn.error"):
        uv = logging.getLogger(name)
        uv.handlers.clear()
        uv.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    for name in _QUIET:
        lg = logging.getLogger(name)
        if lg.level == logging.NOTSET or lg.level < logging.WARNING:
            lg.setLevel(logging.WARNING)


def note(**facts: Any) -> None:
    """Record facts for this request's summary line. No-op outside a request."""
    bag = _facts.get()
    if bag is not None:
        bag.update(facts)


def note_request(request: ExtractRequest, *, keyed: bool) -> None:
    """Shape facts only: sizes and kinds, never content or the key."""
    note(
        doc_type=request.doc_type,
        schema_version=request.schema_version,
        provider_requested=request.provider,
        content_kind="pdf" if request.content_format == "pdf_base64" else "text",
        content_bytes=len(request.content.encode()),
        idempotency_keyed=keyed,
        replayed=False,
    )


def note_client(client: object) -> None:
    """The provider client was resolved and the pipeline is about to run."""
    note(
        provider=getattr(client, "provider", None),
        model=getattr(client, "model", None),
        retry_class="none",
    )


def note_retry(kinds: list[str]) -> None:
    note(retry_class=",".join(kinds))


def note_meta(meta: ExtractMeta) -> None:
    """Final facts of a 200. A replay made no provider call, so it spent nothing."""
    note(
        provider=meta.provider,
        model=meta.model,
        replayed=meta.replayed,
        attempts=0 if meta.replayed else meta.attempts,
        cost_usd=0.0 if meta.replayed else meta.cost_usd,
    )


def _incoming_request_id(scope: Scope) -> str:
    for key, value in scope["headers"]:
        if key == b"x-request-id":
            candidate: str = value.decode("latin-1")
            if _REQUEST_ID_RE.fullmatch(candidate):
                return candidate
            break
    return uuid.uuid4().hex


class RequestContextMiddleware:
    """Request id in/out, contextvars binding, and the single extract.access summary line."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = _incoming_request_id(scope)
        scope[SCOPE_KEY] = rid
        facts: dict[str, Any] = {}
        rid_token = _request_id.set(rid)
        facts_token = _facts.set(facts)
        status = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, rid)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # ServerErrorMiddleware (outside us) renders the 500 after this propagates.
            # The context stays bound so its handler's log line carries the request id;
            # each request runs in its own task, so nothing leaks to the next one.
            facts.setdefault("result", "internal_error")
            self._log(scope, 500, started, facts)
            raise
        self._log(scope, status, started, facts)
        _facts.reset(facts_token)
        _request_id.reset(rid_token)

    @staticmethod
    def _log(scope: Scope, status: int, started: float, facts: MutableMapping[str, Any]) -> None:
        route = scope.get("route")
        # The template ("/v1/extract"), never the raw path or query string.
        path = getattr(route, "path", None) or "unmatched"
        result = facts.pop("result", None) or ("ok" if status < 400 else f"http_{status}")
        _ACCESS.log(
            logging.ERROR if status >= 500 else logging.INFO,
            "request",
            extra={
                "method": scope["method"],
                "route": path,
                "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "result": result,
                **{k: v for k, v in facts.items() if k in ALLOWED_FIELDS},
            },
        )
