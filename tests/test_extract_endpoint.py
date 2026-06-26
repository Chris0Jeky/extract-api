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

    def complete(self, *, system, prompt, json_schema, max_tokens=4096):
        self.calls += 1
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


def _post(client: TestClient, **overrides) -> object:
    body = {"doc_type": "invoice", "schema_version": "v1", "content": "doc", "provider": "openai"}
    body.update(overrides)
    return client.post("/v1/extract", json=body)


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
