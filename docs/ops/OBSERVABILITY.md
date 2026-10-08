# Observability

Structured JSON logs to stdout, one object per line. Code: `api/observability.py`.
Proof that payloads are never logged: `tests/test_observability.py`.

## Never logged

Documents, PDF bytes (or their base64), request payloads, model outputs, the
`Idempotency-Key` value, the `Authorization` header, credentials. Mechanisms:

- The formatter emits only an allowlist of fields from `extra=`; anything else is dropped.
- Exceptions render as type plus stack frames; the message is omitted (it can echo input).
- The access line is built from facts the endpoint notes (kinds, sizes, ids), never from
  bodies. The route is the template (`/v1/extract`), never the raw URL or query string.
- uvicorn's own access log (it prints the raw path and query) is off: `--no-access-log` in
  the Dockerfile CMD and `make dev`. Add it to any other way of launching uvicorn.
- The OpenAI/Anthropic/httpx loggers are held at WARNING (the OpenAI SDK logs the request,
  i.e. the prompt, at DEBUG).
- The one stated exception to "never log upstream text": provider error text
  (`provider error (...)`, `provider timeout (...)`), logged on one line and capped at 300
  characters so operators can diagnose (#21; clients get a sanitized message). It is upstream
  text, so a provider echo of the prompt could appear there; it cannot be proven content-free
  by construction.
- Never set `OPENAI_LOG` or `ANTHROPIC_LOG` in production: the SDKs then log request bodies
  and override the WARNING clamp above.
- uvicorn and `uvicorn.error` are routed through the same redacting handler, and
  `uvicorn.access` is disabled in-process even if `--no-access-log` is forgotten
  (`tests/test_uvicorn_logging.py` runs real uvicorn to prove it).

## Configuration

| Env | Default | Meaning |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. Read once per process (restart to change). Invalid value fails startup. |
| `LOG_FORMAT` | `json` | `text` is an opt-in for local dev; exceptions are redacted exactly as in JSON (type and frames). Invalid value fails startup. |

## Schema

Every line: `ts` (ISO-8601 UTC), `level`, `logger`, `msg`, `request_id` (when inside a request),
plus `exc_type` and `stack` on a logged exception.

Request ids: an inbound `X-Request-ID` matching `^[A-Za-z0-9._-]{1,128}$` is honored, anything
else is replaced by a uuid4 hex. It is echoed in the `X-Request-ID` header of every response,
including errors.

Summary line, logger `extract.access`, one per request, level INFO (ERROR for 5xx):

| Field | Meaning |
| --- | --- |
| `method`, `route`, `status`, `duration_ms` | Always. `route` is the path template or `unmatched`. `status` is null if the client disconnected before a response (`result` is then `client_disconnect`). |
| `result` | Always. `ok` or the `ErrorCode` value (`validation_failed`, `provider_error`, `idempotency_conflict`, `internal_error`, `not_found`, ...). |
| `doc_type`, `schema_version`, `provider_requested`, `content_kind` (`text`/`pdf`), `content_bytes`, `idempotency_keyed`, `replayed` | `/v1/extract` only. Every `/v1/extract` line carries the full set below, with `null` for anything unknown on that path (for example everything on an unparsable body, `attempts` on a provider error). `content_bytes` is the size of the submitted `content` field (base64 length for a PDF). |
| `provider`, `model` | Resolved client; null until a client was built. |
| `attempts` | Provider calls made by this request (0 on a replay). Null when a provider error ended the run. |
| `retry_class` | `none`, or the comma-joined validation error kinds that triggered the retry. |
| `cost_usd` | Spend of this request across attempts; `0.0` on a replay. |

Pipeline retry lines (`extract.pipeline`, WARNING) carry `attempt` and `retry_kinds`.

## The five signals

1. Availability and readiness: `/healthz` is liveness. `/readyz` readiness is added by the
   hosting wave's readiness slice; platform health checks point at them.
2. Request rate, latency, errors: derive from `extract.access` lines (`status`, `result`,
   `duration_ms`, grouped by `route`). Filter `route=/healthz` out of rate figures.
3. CPU and RSS: platform metrics (Render or Railway dashboards) plus the load-test numbers.
   The service emits none itself.
4. Persistent disk utilisation: platform disk metrics for `/data`.
5. Backup age and last restore test: **not applicable.** `/data` holds only the 24h
   idempotency replay cache, which is disposable by contract (ADR 0004), so there is nothing
   to back up. Losing it only drops the replay window.
