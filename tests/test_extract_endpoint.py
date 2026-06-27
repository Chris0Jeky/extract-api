"""POST /v1/extract: happy path + each taxonomy failure, with a stubbed provider.

The provider client is replaced by an in-test scripted fake (monkeypatching
`api.main.get_client`), so these exercise the real endpoint, pipeline, schema, and
error mapping offline and deterministically. The production FixtureClient + `make
smoke` land in T04b; here the fake is a test double, not that client.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.idempotency import SqliteIdempotencyStore
from api.main import create_app
from llm.client import CompletionResult
from llm.errors import ProviderError, ProviderRefusal, ProviderTimeout, ProviderTruncation

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
VALID_JSON = json.dumps(_VALID)
# total != subtotal + tax -> the cross-field model validator raises ValidationError.
INVALID_JSON = json.dumps({**_VALID, "total_minor": 99999})


class _FakeClient:
    """Scripted provider double: str steps return as completion text, Exceptions raise."""

    def __init__(
        self,
        steps: list[object],
        *,
        provider: str = "fake",
        model: str = "fake-model-1",
        cost_usd: float = 0.0012,
        latency_ms: float = 12.5,
        tokens_in: int = 100,
        tokens_out: int = 50,
    ) -> None:
        self.provider = provider
        self._steps = list(steps)
        self._model = model
        self._cost_usd = cost_usd
        self._latency_ms = latency_ms
        self._tokens_in = tokens_in
        self._tokens_out = tokens_out
        self.calls = 0
        self.last_prompt: str | None = None

    def complete(self, *, system, prompt, json_schema, max_tokens=4096):
        self.calls += 1
        self.last_prompt = prompt
        step = self._steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return CompletionResult(
            text=str(step),
            model=self._model,
            tokens_in=self._tokens_in,
            tokens_out=self._tokens_out,
            cost_usd=self._cost_usd,
            latency_ms=self._latency_ms,
            stop_reason="completed",
        )


def _client_with(monkeypatch, fake: _FakeClient) -> TestClient:
    monkeypatch.setattr("api.main.get_client", lambda provider: fake)
    return TestClient(create_app(), raise_server_exceptions=False)


def _post(client: TestClient, *, headers: dict[str, str] | None = None, **overrides) -> object:
    body = {"doc_type": "invoice", "schema_version": "v1", "content": "doc", "provider": "openai"}
    body.update(overrides)
    return client.post("/v1/extract", json=body, headers=headers)


def test_happy_path_returns_data_and_full_meta(monkeypatch):
    fake = _FakeClient([VALID_JSON])
    resp = _post(_client_with(monkeypatch, fake))
    assert resp.status_code == 200
    body = resp.json()

    assert body["data"]["invoice_number"] == "INV-1"
    assert body["data"]["issue_date"] == "2026-01-15"  # date serialized to ISO
    assert body["data"]["due_date"] is None

    meta = body["meta"]
    assert meta["provider"] == "fake"  # the resolved client's provider, not the request
    assert meta["model"] == "fake-model-1"
    assert meta["schema_version"] == "v1"
    assert meta["attempts"] == 1
    assert meta["replayed"] is False
    assert meta["cost_usd"] == pytest.approx(0.0012)
    assert meta["latency_ms"] == pytest.approx(12.5)
    assert fake.calls == 1


def test_field_confidence_is_one_for_present_zero_for_null(monkeypatch):
    resp = _post(_client_with(monkeypatch, _FakeClient([VALID_JSON])))
    confidence = resp.json()["meta"]["field_confidence"]
    assert confidence["invoice_number"] == 1.0  # present
    assert confidence["due_date"] == 0.0  # explicit null
    assert confidence["line_items"] == 0.0  # explicit null
    assert set(confidence) == set(_VALID)  # every top-level field reported


def test_validation_failure_on_both_attempts_returns_422_with_trail(monkeypatch):
    fake = _FakeClient([INVALID_JSON, INVALID_JSON])
    resp = _post(_client_with(monkeypatch, fake))
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "validation_failed"
    assert body["attempts"] == 2
    assert len(body["trail"]) == 2  # one error summary per attempt
    assert fake.calls == 2  # the one feedback retry was used


def test_validation_recovers_on_retry_returns_200(monkeypatch):
    # First attempt invalid, retry valid -> 200 with attempts == 2.
    fake = _FakeClient([INVALID_JSON, VALID_JSON])
    resp = _post(_client_with(monkeypatch, fake))
    assert resp.status_code == 200
    meta = resp.json()["meta"]
    assert meta["attempts"] == 2
    # cost/latency are accumulated across BOTH billed attempts (2x the per-call
    # 0.0012 / 12.5), so meta reflects the total request spend, not the last call.
    assert meta["cost_usd"] == pytest.approx(0.0024)
    assert meta["latency_ms"] == pytest.approx(25.0)
    assert fake.calls == 2


def test_provider_timeout_maps_to_504(monkeypatch):
    fake = _FakeClient([ProviderTimeout(provider="fake", detail="slow")])
    resp = _post(_client_with(monkeypatch, fake))
    assert resp.status_code == 504
    assert resp.json()["error"] == "provider_timeout"


@pytest.mark.parametrize(
    "exc",
    [
        ProviderRefusal(provider="fake", reason="policy"),
        ProviderTruncation(provider="fake", reason="max_output_tokens"),
        ProviderError(provider="fake", detail="boom"),
    ],
)
def test_provider_failures_map_to_502(monkeypatch, exc):
    resp = _post(_client_with(monkeypatch, _FakeClient([exc])))
    assert resp.status_code == 502
    assert resp.json()["error"] == "provider_error"


def test_unknown_schema_version_renders_unsupported_doc_type(monkeypatch):
    # A registered doc_type with an unregistered version misses the registry, which
    # raises UnknownSchema BEFORE any provider call -> the taxonomy, not a 500.
    fake = _FakeClient([VALID_JSON])
    resp = _post(_client_with(monkeypatch, fake), schema_version="v2")
    assert resp.status_code == 422
    assert resp.json()["error"] == "unsupported_doc_type"
    assert fake.calls == 0  # resolve fails before the client is called


def test_empty_content_is_rejected_before_any_provider_call(monkeypatch):
    # Whitespace-only content fails loud as validation_failed without a billed call.
    fake = _FakeClient([VALID_JSON])
    resp = _post(_client_with(monkeypatch, fake), content="   ")
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_failed"
    assert fake.calls == 0


def test_missing_required_field_renders_validation_failed():
    # A missing required field is a RequestValidationError -> validation_failed via the
    # T05 handler, not FastAPI's default 422 body. Validation runs before the handler.
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.post("/v1/extract", json={"doc_type": "invoice", "schema_version": "v1"})
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_failed"


def test_extra_forbidden_key_renders_validation_failed():
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.post(
        "/v1/extract",
        json={"doc_type": "invoice", "schema_version": "v1", "content": "x", "bogus": 1},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_failed"


def test_missing_doc_type_renders_validation_failed():
    # An OMITTED doc_type is a malformed body (validation_failed), not unsupported_doc_type
    # which is reserved for a genuinely out-of-Literal doc_type value.
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.post("/v1/extract", json={"schema_version": "v1", "content": "x"})
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_failed"


def test_bad_doc_type_wins_over_other_field_errors():
    # An out-of-Literal doc_type renders unsupported_doc_type even when other fields are
    # also invalid (content is missing here): doc_type classification takes precedence.
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.post("/v1/extract", json={"doc_type": "passport"})
    assert resp.status_code == 422
    assert resp.json()["error"] == "unsupported_doc_type"


def test_unexpected_client_error_renders_internal_error(monkeypatch):
    # A non-provider exception escaping the pipeline maps to internal_error (500) via the
    # T05 catch-all, still carrying exactly one taxonomy code (not a bare 500).
    resp = _post(_client_with(monkeypatch, _FakeClient([RuntimeError("boom")])))
    assert resp.status_code == 500
    assert resp.json()["error"] == "internal_error"


# --- T12: idempotency wiring (store consulted before any model call) ---


def _store(tmp_path) -> SqliteIdempotencyStore:
    return SqliteIdempotencyStore(str(tmp_path / "i.sqlite"))


def _client_with_store(monkeypatch, fake: _FakeClient, store) -> TestClient:
    monkeypatch.setattr("api.main.get_client", lambda provider: fake)
    return TestClient(create_app(idempotency_store=store), raise_server_exceptions=False)


def test_same_key_same_payload_replays_without_a_model_call(monkeypatch, tmp_path):
    # One canned step only: a second model call would pop an empty list and error, so this
    # also proves the replay path never reaches the client.
    fake = _FakeClient([VALID_JSON])
    client = _client_with_store(monkeypatch, fake, _store(tmp_path))
    headers = {"Idempotency-Key": "abc123"}

    first = _post(client, headers=headers)
    assert first.status_code == 200
    assert first.json()["meta"]["replayed"] is False
    assert fake.calls == 1

    second = _post(client, headers=headers)
    assert second.status_code == 200
    assert second.json()["meta"]["replayed"] is True
    assert second.json()["data"] == first.json()["data"]
    assert fake.calls == 1  # the replay did not call the model again


def test_same_key_different_payload_returns_409(monkeypatch, tmp_path):
    fake = _FakeClient([VALID_JSON])  # the conflict must be caught before a second call
    client = _client_with_store(monkeypatch, fake, _store(tmp_path))
    headers = {"Idempotency-Key": "dup"}

    assert _post(client, headers=headers).status_code == 200
    # Same key, different content -> different payload hash -> conflict.
    resp = _post(client, headers=headers, content="a completely different document")
    assert resp.status_code == 409
    assert resp.json()["error"] == "idempotency_conflict"
    assert fake.calls == 1  # detected before any model call


def test_different_keys_each_run(monkeypatch, tmp_path):
    fake = _FakeClient([VALID_JSON, VALID_JSON])
    client = _client_with_store(monkeypatch, fake, _store(tmp_path))
    r1 = _post(client, headers={"Idempotency-Key": "k1"})
    r2 = _post(client, headers={"Idempotency-Key": "k2"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["meta"]["replayed"] is False
    assert fake.calls == 2  # distinct keys -> two model calls


def test_failed_extraction_is_not_stored_so_retry_runs(monkeypatch, tmp_path):
    # First attempt fails (provider error, not stored); a retry with the same key re-runs
    # and can succeed, rather than replaying the failure.
    fake = _FakeClient([ProviderError(provider="fake", detail="boom"), VALID_JSON])
    client = _client_with_store(monkeypatch, fake, _store(tmp_path))
    headers = {"Idempotency-Key": "retry-me"}

    first = _post(client, headers=headers)
    assert first.status_code == 502
    second = _post(client, headers=headers)
    assert second.status_code == 200
    assert second.json()["meta"]["replayed"] is False
    assert fake.calls == 2


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_idempotency_key_is_rejected(monkeypatch, tmp_path, blank):
    # A present-but-blank header must fail loud (not become a degenerate shared key), and
    # before any model call - mirroring the empty-content guard.
    fake = _FakeClient([VALID_JSON])
    client = _client_with_store(monkeypatch, fake, _store(tmp_path))
    resp = _post(client, headers={"Idempotency-Key": blank})
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_failed"
    assert fake.calls == 0


def test_oversized_idempotency_key_is_rejected(monkeypatch, tmp_path):
    fake = _FakeClient([VALID_JSON])
    client = _client_with_store(monkeypatch, fake, _store(tmp_path))
    resp = _post(client, headers={"Idempotency-Key": "x" * 256})
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_failed"
    assert fake.calls == 0


# --- T14: PDF content (base64 PDF -> extracted text drives the extraction) ---


def _pdf_b64(text: str) -> str:
    import base64

    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    raw = doc.tobytes()
    doc.close()
    return base64.b64encode(raw).decode()


def test_pdf_content_is_extracted_and_drives_extraction(monkeypatch):
    fake = _FakeClient([VALID_JSON])
    client = _client_with(monkeypatch, fake)
    resp = _post(client, content=_pdf_b64("Invoice body text 42"), content_format="pdf_base64")
    assert resp.status_code == 200
    # The pipeline received the EXTRACTED text, not the base64 blob.
    assert fake.last_prompt is not None
    assert "Invoice body text 42" in fake.last_prompt


def test_bad_pdf_at_endpoint_returns_422(monkeypatch):
    import base64

    fake = _FakeClient([VALID_JSON])
    client = _client_with(monkeypatch, fake)
    not_pdf = base64.b64encode(b"plainly not a pdf").decode()
    resp = _post(client, content=not_pdf, content_format="pdf_base64")
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_failed"
    assert fake.calls == 0  # bad PDF fails loud before any model call


def test_unsupported_schema_is_caught_before_pdf_extraction(monkeypatch):
    import base64

    # An unsupported schema_version fails as unsupported_doc_type BEFORE any PDF work, even
    # with a bad PDF (which would otherwise be validation_failed): schema is checked first.
    fake = _FakeClient([VALID_JSON])
    client = _client_with(monkeypatch, fake)
    bad_pdf = base64.b64encode(b"not a pdf at all").decode()
    resp = _post(client, schema_version="v2", content=bad_pdf, content_format="pdf_base64")
    assert resp.status_code == 422
    assert resp.json()["error"] == "unsupported_doc_type"
    assert fake.calls == 0


def test_default_store_is_built_lazily_from_env(monkeypatch, tmp_path):
    # No injected store: the default store is built lazily from IDEMPOTENCY_DB_PATH on the
    # first keyed request (not at import), and replay works through it.
    monkeypatch.setenv("IDEMPOTENCY_DB_PATH", str(tmp_path / "default.sqlite"))
    fake = _FakeClient([VALID_JSON])
    monkeypatch.setattr("api.main.get_client", lambda provider: fake)
    client = TestClient(create_app(), raise_server_exceptions=False)  # no store injected
    headers = {"Idempotency-Key": "lazy-1"}

    first = _post(client, headers=headers)
    assert first.status_code == 200
    second = _post(client, headers=headers)
    assert second.json()["meta"]["replayed"] is True
    assert fake.calls == 1
    assert (tmp_path / "default.sqlite").exists()  # built on first keyed use, in the tmp dir
