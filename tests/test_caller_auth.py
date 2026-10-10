"""Caller authentication on POST /v1/extract.

Owner decision `extract-api-caller-auth`, answered (a) on 2026-10-10 (agent-hq PR 356): callers
send `Authorization: Bearer <key>`; the service holds only SHA-256 hashes, in the secret
`EXTRACT_API_KEY_SHA256S`; two keys can be valid at once; a service with no hashes refuses to
serve extractions; /healthz and /readyz stay open. That approval is what permits the new
`unauthorized` (401) error code.
"""

from __future__ import annotations

import hashlib
import json
import logging

import pytest
from fastapi.testclient import TestClient

from api import auth
from api.idempotency import SqliteIdempotencyStore
from api.main import create_app
from caller_keys import AUTH, TEST_KEY, TEST_KEY_SHA256

ENV = "EXTRACT_API_KEY_SHA256S"
SECOND_KEY = "second-test-caller-key-not-a-secret"
SECOND_SHA256 = hashlib.sha256(SECOND_KEY.encode()).hexdigest()
INVOICE = {
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
BODY = {"doc_type": "invoice", "schema_version": "v1", "content": "doc", "provider": "openai"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    """A fixture-mode app (no provider, no spend); callers set ENV before building it."""
    monkeypatch.setenv("LLM_PROVIDER_MODE", "fixture")
    monkeypatch.setenv("FIXTURE_CANNED_TEXT", json.dumps(INVOICE))

    def make() -> TestClient:
        store = SqliteIdempotencyStore(str(tmp_path / "idem.sqlite"))
        return TestClient(create_app(idempotency_store=store), raise_server_exceptions=False)

    return make


def _bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_the_configured_key_is_accepted(client):
    resp = client().post("/v1/extract", json=BODY, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["invoice_number"] == "INV-1"


def test_scheme_is_case_insensitive(client):
    resp = client().post("/v1/extract", json=BODY, headers={"Authorization": f"bEaReR {TEST_KEY}"})
    assert resp.status_code == 200


def test_missing_header_is_401_in_the_standard_envelope(client):
    resp = client().post("/v1/extract", json=BODY)
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"] == "unauthorized"
    assert body["detail"]
    assert resp.headers["WWW-Authenticate"] == "Bearer"
    assert resp.headers["X-Request-ID"]


@pytest.mark.parametrize(
    "header",
    [
        "",
        "Bearer",
        "Bearer ",
        f"Basic {TEST_KEY}",
        f"Token {TEST_KEY}",
        TEST_KEY,
        f"Bearer {TEST_KEY} extra",
        f"Bearer {TEST_KEY}x",
        f"Bearer {TEST_KEY[:-1]}",
        "Bearer not-the-key",
        f"Bearer {TEST_KEY_SHA256}",  # presenting the stored hash must not authenticate
    ],
)
def test_malformed_or_wrong_credentials_are_401(client, header):
    resp = client().post("/v1/extract", json=BODY, headers={"Authorization": header})
    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_a_failed_check_never_reaches_the_provider(client, monkeypatch):
    def forbidden(provider):
        raise AssertionError("the provider seam was reached without a valid key")

    monkeypatch.setattr("api.main.get_client", forbidden)
    resp = client().post("/v1/extract", json=BODY, headers=_bearer("wrong"))
    assert resp.status_code == 401


def test_auth_runs_before_the_body_is_read(client):
    # An unauthenticated caller learns nothing about the request shape: not-JSON is a 401,
    # not a 422 validation_failed.
    resp = client().post(
        "/v1/extract", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 401


def test_the_route_is_guarded_for_every_method(client):
    assert client().get("/v1/extract").status_code == 401
    assert client().get("/v1/extract", headers=AUTH).status_code == 405


def test_health_and_readiness_stay_open(client, monkeypatch, tmp_path):
    monkeypatch.setenv("IDEMPOTENCY_DB_PATH", str(tmp_path / "ready.sqlite"))
    app = client()
    assert app.get("/healthz").status_code == 200
    assert app.get("/readyz").status_code == 200


def test_unknown_routes_are_guarded_too(client):
    # Guard by default: only /healthz and /readyz are open, so a path that merely routes to
    # /v1/extract by some other spelling cannot slip past a path comparison.
    assert client().get("/nope").status_code == 401
    assert client().get("/nope", headers=AUTH).status_code == 404


@pytest.mark.parametrize("suffix", ["%0A", "%0a", "%0D%0A", "%20", "/", "%2F"])
def test_alternate_spellings_of_the_extract_path_cannot_bypass_auth(client, monkeypatch, suffix):
    # uvicorn decodes /v1/extract%0A to "/v1/extract\n", which Starlette's route regex
    # (`$` matches before a trailing newline) still routes to extract().
    def forbidden(provider):
        raise AssertionError("the provider seam was reached without a valid key")

    monkeypatch.setattr("api.main.get_client", forbidden)
    resp = client().post(f"/v1/extract{suffix}", json=BODY)
    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


def test_a_newline_spelling_with_a_valid_key_is_still_served(client):
    # The same quirk, authenticated: the route runs, so the cap and the check both ran first.
    assert client().post("/v1/extract%0A", json=BODY, headers=AUTH).status_code == 200


def test_a_root_path_prefix_does_not_unguard_the_route(client, monkeypatch, tmp_path):
    app = create_app(
        idempotency_store=SqliteIdempotencyStore(str(tmp_path / "rp.sqlite")),
    )
    prefixed = TestClient(app, root_path="/api", raise_server_exceptions=False)
    assert prefixed.post("/api/v1/extract", json=BODY).status_code == 401
    assert prefixed.post("/api/v1/extract", json=BODY, headers=AUTH).status_code == 200
    monkeypatch.setenv("IDEMPOTENCY_DB_PATH", str(tmp_path / "ready.sqlite"))
    assert prefixed.get("/api/healthz").status_code == 200  # still open under the prefix


@pytest.mark.parametrize("path", ["/healthz", "/readyz", "/api/healthz"])
def test_only_the_health_probes_are_open(path):
    scope = {"type": "http", "path": path, "root_path": "/api" if path.startswith("/api") else ""}
    assert auth.is_open_path(scope)


@pytest.mark.parametrize(
    "path", ["/v1/extract", "/v1/extract\n", "/healthz\n", "/healthz/", "/nope", "/readyz%0A", ""]
)
def test_everything_else_is_guarded(path):
    assert not auth.is_open_path({"type": "http", "path": path})


def test_two_keys_are_valid_at_once(client, monkeypatch):
    monkeypatch.setenv(ENV, f"{TEST_KEY_SHA256},{SECOND_SHA256}")
    app = client()
    assert app.post("/v1/extract", json=BODY, headers=_bearer(TEST_KEY)).status_code == 200
    assert app.post("/v1/extract", json=BODY, headers=_bearer(SECOND_KEY)).status_code == 200
    assert app.post("/v1/extract", json=BODY, headers=_bearer("third")).status_code == 401


def test_rotation_retires_a_key_by_dropping_its_hash(client, monkeypatch):
    monkeypatch.setenv(ENV, SECOND_SHA256)
    app = client()
    assert app.post("/v1/extract", json=BODY, headers=_bearer(SECOND_KEY)).status_code == 200
    assert app.post("/v1/extract", json=BODY, headers=AUTH).status_code == 401


def test_list_tolerates_spaces_blank_entries_and_uppercase(client, monkeypatch):
    monkeypatch.setenv(ENV, f" {SECOND_SHA256.upper()} , ,{TEST_KEY_SHA256},")
    app = client()
    assert app.post("/v1/extract", json=BODY, headers=_bearer(SECOND_KEY)).status_code == 200
    assert app.post("/v1/extract", json=BODY, headers=AUTH).status_code == 200


@pytest.mark.parametrize("value", [None, "", "  ", " , ,"])
def test_no_hashes_configured_fails_closed(client, monkeypatch, value):
    if value is None:
        monkeypatch.delenv(ENV)
    else:
        monkeypatch.setenv(ENV, value)
    resp = client().post("/v1/extract", json=BODY, headers=AUTH)
    assert resp.status_code == 500
    assert resp.json()["error"] == "internal_error"
    assert "WWW-Authenticate" not in resp.headers  # a service fault, not the caller's key


def test_no_hashes_still_serves_the_health_probes(client, monkeypatch, tmp_path):
    monkeypatch.delenv(ENV)
    monkeypatch.setenv("IDEMPOTENCY_DB_PATH", str(tmp_path / "ready.sqlite"))
    app = client()
    assert app.get("/healthz").status_code == 200
    assert app.get("/readyz").status_code == 200


@pytest.mark.parametrize(
    "value",
    [TEST_KEY, TEST_KEY_SHA256[:-1], TEST_KEY_SHA256 + "0", "g" * 64, f"{TEST_KEY_SHA256},oops"],
)
def test_a_malformed_entry_fails_startup_without_echoing_it(client, monkeypatch, value):
    # A plaintext key pasted where a hash belongs must not end up in the startup error.
    monkeypatch.setenv(ENV, value)
    with pytest.raises(ValueError, match=ENV) as exc:
        client()
    assert TEST_KEY not in str(exc.value) and "oops" not in str(exc.value)


def test_every_configured_hash_is_compared_in_constant_time(client, monkeypatch):
    calls: list[tuple[bytes, bytes]] = []
    real = auth.hmac.compare_digest

    def spy(a: bytes, b: bytes) -> bool:
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setenv(ENV, f"{TEST_KEY_SHA256},{SECOND_SHA256}")
    app = client()
    monkeypatch.setattr(auth.hmac, "compare_digest", spy)
    # The first hash matches, yet the second is still compared: no early exit to time.
    assert app.post("/v1/extract", json=BODY, headers=AUTH).status_code == 200
    assert len(calls) == 2


def test_neither_the_token_nor_its_hash_is_ever_logged(client, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    app = client()
    app.post("/v1/extract", json=BODY, headers=AUTH)
    app.post("/v1/extract", json=BODY, headers=_bearer("wrong-token-canary"))
    monkeypatch.delenv(ENV)
    client().post("/v1/extract", json=BODY, headers=AUTH)
    assert caplog.records
    text = " ".join(repr(vars(r)) + r.getMessage() for r in caplog.records)
    secrets = (TEST_KEY, TEST_KEY_SHA256, "wrong-token-canary")
    assert not any(s in text for s in secrets)


def test_the_access_line_names_the_route_and_the_result(client, caplog):
    caplog.set_level(logging.INFO)
    client().post("/v1/extract", json=BODY, headers=_bearer("wrong"))
    (line,) = [r for r in caplog.records if r.name == "extract.access"]
    assert (line.route, line.status, line.result) == ("/v1/extract", 401, "unauthorized")
