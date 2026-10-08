"""Observability: the redaction proof, the access line, request ids, the formatter.

The proof drives the real app through every outcome (200, 422, 409, 502, 500) with a unique
canary planted in each place a payload could hide, captures EVERYTHING logged at DEBUG on the
root logger, and asserts the canary is nowhere: not in a record's message or args, not in the
JSON text the real handler wrote to stdout. A precondition per scenario proves the canary did
reach the code under test, so a pass cannot mean "the canary never got in".
"""

from __future__ import annotations

import base64
import json
import logging
import re

import pymupdf
import pytest
from fastapi.testclient import TestClient

from api.idempotency import SqliteIdempotencyStore
from api.main import create_app
from api.observability import JsonFormatter, configure_logging
from llm.client import CompletionResult, FixtureClient
from llm.errors import ProviderError

CANARY = "CANARY-7f3a9c1e-DO-NOT-LOG"
_VALID = {
    "invoice_number": "INV-1",
    "issue_date": "2026-01-15",
    "due_date": None,
    "currency": "GBP",
    "subtotal_minor": 10000,
    "tax_minor": 2000,
    "total_minor": 12000,
    "vendor_name": "Acme Ltd",
    "vendor_tax_id": None,
    "buyer_name": None,
    "line_items": None,
}
VALID = json.dumps(_VALID)
# total != subtotal + tax -> value_error; the canary rides in vendor_name (model output).
INVALID_WITH_CANARY = json.dumps({**_VALID, "total_minor": 99999, "vendor_name": CANARY})


def _pdf_b64(text: str) -> str:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return base64.b64encode(data).decode()


class _Scripted:
    """Provider double: str steps return as text, Exceptions raise. Records prompts."""

    provider = "fake"
    model = "fake-model-1"

    def __init__(self, steps: list[object], cost_usd: float = 0.0012) -> None:
        self._steps = list(steps)
        self._cost = cost_usd
        self.prompts: list[str] = []

    def complete(self, *, system, prompt, json_schema, max_tokens=4096):
        self.prompts.append(prompt)
        step = self._steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return CompletionResult(
            text=str(step),
            model=self.model,
            tokens_in=1,
            tokens_out=1,
            cost_usd=self._cost,
            latency_ms=1.0,
            stop_reason="completed",
        )


@pytest.fixture
def logs(caplog, capsys):
    """Capture everything at DEBUG on the root logger: caplog records + real handler stdout."""
    caplog.set_level(logging.DEBUG)

    class Captured:
        def stdout_lines(self) -> list[dict]:
            out = capsys.readouterr().out
            self._text = getattr(self, "_text", "") + out
            return [json.loads(line) for line in self._text.splitlines() if line.startswith("{")]

        def access(self) -> list[dict]:
            return [r for r in self.stdout_lines() if r["logger"] == "extract.access"]

        def assert_clean(self, *needles: str) -> None:
            self.stdout_lines()  # drain
            fmt = JsonFormatter()
            # The TestClient's own httpx logger records the URL the TEST sent; it is the
            # caller's side of the wire, not the service, so it is out of scope.
            haystacks = [line for line in self._text.splitlines() if '"logger":"httpx' not in line]
            for rec in caplog.records:
                if rec.name.startswith(("httpx", "httpcore")):
                    continue
                haystacks += [rec.getMessage(), repr(rec.args), fmt.format(rec)]
            assert caplog.records, "nothing was logged; the capture is not working"
            for needle in needles:
                for hay in haystacks:
                    assert needle not in hay, f"{needle!r} leaked into logs: {hay[:300]}"

    return Captured()


@pytest.fixture
def client_factory(tmp_path):
    def make(fake: object | None = None, monkeypatch=None) -> TestClient:
        if fake is not None:
            monkeypatch.setattr("api.main.get_client", lambda provider: fake)
        store = SqliteIdempotencyStore(str(tmp_path / "idem.sqlite"))
        return TestClient(create_app(idempotency_store=store), raise_server_exceptions=False)

    return make


def _body(**kw) -> dict:
    return {"doc_type": "invoice", "schema_version": "v1", "content": "doc", **kw}


# ---------------------------------------------------------------- the redaction proof


def test_canary_never_logged_on_200_text_and_pdf(monkeypatch, client_factory, logs):
    monkeypatch.setenv("LLM_PROVIDER_MODE", "fixture")
    monkeypatch.setenv("FIXTURE_CANNED_TEXT", VALID)
    client = client_factory()
    headers = {"Idempotency-Key": f"key-{CANARY}", "Authorization": f"Bearer {CANARY}"}

    text = client.post("/v1/extract", json=_body(content=f"Invoice {CANARY}"), headers=headers)
    pdf_b64 = _pdf_b64(f"Invoice {CANARY}")
    pdf = client.post(
        "/v1/extract", json=_body(content=pdf_b64, content_format="pdf_base64"), headers=headers
    )
    assert text.status_code == 200
    # The same key with a different payload is a 409, which also must not log the key.
    assert pdf.status_code == 409
    other = client.post(
        "/v1/extract", json=_body(content=pdf_b64, content_format="pdf_base64")
    )  # keyless, so it runs
    assert other.status_code == 200
    logs.assert_clean(CANARY, pdf_b64, pdf_b64[:40], base64.b64encode(CANARY.encode()).decode())


def test_canary_never_logged_on_422_validation_trail(monkeypatch, client_factory, logs):
    monkeypatch.setenv("LLM_PROVIDER_MODE", "fixture")
    monkeypatch.setenv("FIXTURE_CANNED_TEXT", INVALID_WITH_CANARY)
    prompts: list[str] = []
    real = FixtureClient.complete

    def spy(self, *, system, prompt, json_schema, max_tokens=4096):
        prompts.append(prompt)
        return real(
            self, system=system, prompt=prompt, json_schema=json_schema, max_tokens=max_tokens
        )

    monkeypatch.setattr(FixtureClient, "complete", spy)
    resp = client_factory().post(
        "/v1/extract",
        json=_body(content=f"Invoice {CANARY}"),
        headers={"Idempotency-Key": CANARY, "Authorization": f"Bearer {CANARY}"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_failed"
    # Precondition: the model output (with the canary) really went through the retry prompt.
    assert len(prompts) == 2 and CANARY in prompts[1]
    logs.assert_clean(CANARY)


def test_canary_never_logged_on_502_provider_error(monkeypatch, client_factory, logs):
    fake = _Scripted([ProviderError(provider="fake", detail="upstream said no")])
    resp = client_factory(fake, monkeypatch).post(
        "/v1/extract",
        json=_body(content=f"Invoice {CANARY}"),
        headers={"Idempotency-Key": CANARY, "Authorization": f"Bearer {CANARY}"},
    )
    assert resp.status_code == 502
    assert fake.prompts == [f"Invoice {CANARY}"]  # precondition: canary reached the provider
    logs.assert_clean(CANARY)
    (line,) = logs.access()
    assert line["status"] == 502 and line["result"] == "provider_error"


def test_canary_never_logged_on_500_even_when_exception_message_echoes_it(
    monkeypatch, client_factory, logs
):
    # An SDK/library exception whose message repeats the prompt: the traceback message must
    # not reach the JSON log (type and frames only).
    fake = _Scripted([RuntimeError(f"boom while handling {CANARY}")])
    resp = client_factory(fake, monkeypatch).post(
        "/v1/extract", json=_body(content=f"Invoice {CANARY}")
    )
    assert resp.status_code == 500
    assert resp.json()["error"] == "internal_error"
    assert resp.headers["x-request-id"]
    logs.assert_clean(CANARY)
    lines = logs.stdout_lines()
    assert any(line.get("exc_type") == "RuntimeError" for line in lines)
    (access,) = [line for line in lines if line["logger"] == "extract.access"]
    assert access["status"] == 500 and access["result"] == "internal_error"


def test_query_string_and_unknown_path_are_not_logged(client_factory, logs):
    resp = client_factory().get(f"/nope/{CANARY}?token={CANARY}")
    assert resp.status_code == 404
    logs.assert_clean(CANARY)
    (line,) = logs.access()
    assert line["route"] == "unmatched" and line["result"] == "not_found"


# ---------------------------------------------------------------- the access line


def test_access_line_on_200_with_retry(monkeypatch, client_factory, logs):
    fake = _Scripted([INVALID_WITH_CANARY, VALID], cost_usd=0.5)
    resp = client_factory(fake, monkeypatch).post(
        "/v1/extract",
        json=_body(content="abcde", provider="anthropic"),
        headers={"Idempotency-Key": "k1"},
    )
    assert resp.status_code == 200
    (line,) = logs.access()
    assert line["request_id"] == resp.headers["x-request-id"]
    assert line["method"] == "POST" and line["route"] == "/v1/extract" and line["status"] == 200
    assert isinstance(line["duration_ms"], float)
    assert line["doc_type"] == "invoice" and line["schema_version"] == "v1"
    assert line["provider_requested"] == "anthropic" and line["provider"] == "fake"
    assert line["model"] == "fake-model-1" and line["attempts"] == 2
    assert line["retry_class"] == "value_error" and line["result"] == "ok"
    assert line["cost_usd"] == pytest.approx(1.0)  # both attempts billed
    assert line["replayed"] is False and line["idempotency_keyed"] is True
    assert line["content_kind"] == "text" and line["content_bytes"] == 5
    assert "k1" not in json.dumps(line)  # the key itself is never logged


def test_access_line_on_replay_spends_nothing(monkeypatch, client_factory, logs):
    client = client_factory(_Scripted([VALID], cost_usd=0.5), monkeypatch)
    for _ in range(2):
        assert (
            client.post("/v1/extract", json=_body(), headers={"Idempotency-Key": "k"}).status_code
            == 200
        )
    first, second = logs.access()
    assert first["cost_usd"] == 0.5 and first["attempts"] == 1 and first["replayed"] is False
    assert second["cost_usd"] == 0.0 and second["attempts"] == 0 and second["replayed"] is True


def test_access_line_on_422(monkeypatch, client_factory, logs):
    fake = _Scripted([INVALID_WITH_CANARY, INVALID_WITH_CANARY], cost_usd=0.25)
    resp = client_factory(fake, monkeypatch).post("/v1/extract", json=_body(content="xy"))
    assert resp.status_code == 422
    (line,) = logs.access()
    assert line["status"] == 422 and line["result"] == "validation_failed"
    assert line["provider"] == "fake" and line["model"] == "fake-model-1"
    assert line["attempts"] == 2 and line["retry_class"] == "value_error"
    assert line["cost_usd"] == pytest.approx(0.5)
    assert line["replayed"] is False and line["idempotency_keyed"] is False
    assert line["content_kind"] == "text" and line["content_bytes"] == 2


def test_access_line_pdf_content_kind(monkeypatch, client_factory, logs):
    b64 = _pdf_b64("hello")
    client_factory(_Scripted([VALID]), monkeypatch).post(
        "/v1/extract", json=_body(content=b64, content_format="pdf_base64")
    )
    (line,) = logs.access()
    assert line["content_kind"] == "pdf" and line["content_bytes"] == len(b64)


# ---------------------------------------------------------------- request ids


def test_request_id_generated_and_echoed_on_ok_and_error(client_factory):
    client = client_factory()
    ok = client.get("/healthz")
    err = client.post("/v1/extract", json={"nope": 1})
    assert err.status_code == 422
    for resp in (ok, err):
        assert re.fullmatch(r"[0-9a-f]{32}", resp.headers["x-request-id"])
    assert ok.headers["x-request-id"] != err.headers["x-request-id"]


def test_valid_inbound_request_id_is_honored_and_logged(client_factory, logs):
    resp = client_factory().get("/healthz", headers={"X-Request-ID": "abc.DEF_123-x"})
    assert resp.headers["x-request-id"] == "abc.DEF_123-x"
    (line,) = logs.access()
    assert line["request_id"] == "abc.DEF_123-x"


@pytest.mark.parametrize("bad", ["a" * 300, "has space", "semi;colon", "<script>", ""])
def test_invalid_inbound_request_id_is_replaced(client_factory, bad):
    resp = client_factory().get("/healthz", headers={"X-Request-ID": bad})
    assert re.fullmatch(r"[0-9a-f]{32}", resp.headers["x-request-id"])


def test_request_id_with_newline_is_replaced(client_factory):
    # Sent as raw ASGI bytes: a real HTTP stack rejects this, but the middleware must not
    # trust it either way (log injection).
    from api.observability import _incoming_request_id

    rid = _incoming_request_id({"headers": [(b"x-request-id", b'ok\n{"forged":1}')]})
    assert re.fullmatch(r"[0-9a-f]{32}", rid)


# ---------------------------------------------------------------- formatter and config


def _record(**extra) -> logging.LogRecord:
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "msg %s", ("a",), None)
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


def test_formatter_drops_non_allowlisted_extras():
    line = json.loads(JsonFormatter().format(_record(model="m", payload=CANARY, content=CANARY)))
    assert line["model"] == "m" and line["msg"] == "msg a" and line["level"] == "INFO"
    assert "payload" not in line and "content" not in line
    assert CANARY not in json.dumps(line)
    assert line["ts"].endswith("+00:00")


def test_formatter_caps_long_values_and_drops_exception_message():
    try:
        raise ValueError(CANARY)
    except ValueError:
        import sys

        rec = _record(model="x" * 1000)
        rec.exc_info = sys.exc_info()
    line = json.loads(JsonFormatter().format(rec))
    assert len(line["model"]) == 256
    assert line["exc_type"] == "ValueError" and CANARY not in json.dumps(line)


def test_configure_logging_is_idempotent_and_keeps_caplog_handler(caplog):
    root = logging.getLogger()
    configure_logging()
    configure_logging()
    create_app()
    assert caplog.handler in root.handlers
    assert sum(1 for h in root.handlers if getattr(h, "_extract_observability", False)) == 1
    # SDK debug loggers (they log request bodies) are held at WARNING or above.
    assert logging.getLogger("openai").getEffectiveLevel() >= logging.WARNING


@pytest.mark.parametrize(
    ("name", "value"), [("LOG_LEVEL", "LOUD"), ("LOG_LEVEL", "NOTSET"), ("LOG_FORMAT", "yaml")]
)
def test_invalid_logging_env_fails_loud(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        configure_logging()


def test_formatter_stringifies_and_bounds_unexpected_value_types():
    line = json.loads(JsonFormatter().format(_record(model={"k": "v"}, retry_kinds=["a", 1])))
    assert line["model"] == "{'k': 'v'}" and line["retry_kinds"] == ["a", 1]


def test_text_format_is_opt_in_and_json_is_restored(monkeypatch, capsys):
    monkeypatch.setenv("LOG_FORMAT", "text")
    configure_logging()
    logging.getLogger("t").warning("plain line")
    assert "WARNING t plain line" in capsys.readouterr().out
    monkeypatch.delenv("LOG_FORMAT")
    configure_logging()  # back to the default for the rest of the session
    logging.getLogger("t").warning("json line")
    assert json.loads(capsys.readouterr().out.strip())["msg"] == "json line"


def test_text_format_redacts_exceptions_like_json(monkeypatch, capsys, caplog):
    monkeypatch.setenv("LOG_FORMAT", "text")
    configure_logging()
    try:
        try:
            raise ValueError(f"bad input {CANARY}")
        except ValueError:
            # caplog's handler formats first and caches the message in record.exc_text;
            # our formatter must not reuse that cache.
            logging.getLogger("t").exception("it failed")
    finally:
        monkeypatch.delenv("LOG_FORMAT")
        configure_logging()
    out = capsys.readouterr().out
    assert CANARY not in out
    assert "it failed" in out and "ValueError" in out and "test_observability.py" in out


def test_lifespan_scope_passes_through_the_middleware(client_factory):
    with client_factory() as client:  # entering the context runs the ASGI lifespan
        assert client.get("/healthz").status_code == 200


def test_lone_surrogate_content_is_sized_not_a_500(monkeypatch, client_factory, logs):
    # JSON "D800" decodes to a lone surrogate; plain .encode() raised on it.
    raw = rb'{"doc_type": "invoice", "content": "\ud800"}'
    resp = client_factory(_Scripted([VALID]), monkeypatch).post(
        "/v1/extract", content=raw, headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 200
    (line,) = logs.access()
    assert line["content_bytes"] == 3
