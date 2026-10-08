"""The deploy descriptors keep ADR 0005's invariants, so an edit that would scale out the
per-instance idempotency store, lose the disk, or commit a secret value fails CI."""

import json
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from api.main import create_app

_ROOT = Path(__file__).resolve().parent.parent
_SECRETS = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_API_KEY"}


def _render_service() -> dict:
    blueprint = yaml.safe_load((_ROOT / "render.yaml").read_text(encoding="utf-8"))
    (service,) = blueprint["services"]
    return service


def _railway() -> dict:
    return json.loads((_ROOT / "railway.json").read_text(encoding="utf-8"))


def test_render_runs_exactly_one_instance_with_a_data_disk():
    service = _render_service()
    assert service["numInstances"] == 1
    assert "scaling" not in service  # autoscaling would add replicas with separate stores
    assert service["disk"]["mountPath"] == "/data"
    env = {var["key"]: var for var in service["envVars"]}
    assert env["IDEMPOTENCY_DB_PATH"]["value"].startswith("/data/")
    assert env["IDEMPOTENCY_REQUIRE_PERSISTENT_MOUNT"]["value"] == "1"


def test_render_promotes_the_ci_image_rather_than_building():
    service = _render_service()
    assert service["runtime"] == "image"
    assert service["image"]["url"].startswith("ghcr.io/chris0jeky/extract-api:")
    assert "creds" not in service["image"]  # a public package needs no stored credential


def test_render_starts_safe_and_names_secrets_only():
    env = {var["key"]: var for var in _render_service()["envVars"]}
    assert env["LLM_PROVIDER_MODE"]["value"] == "fixture"
    # The spend cap must be set: unset disables api/budget.py's guard entirely.
    assert float(env["EXTRACT_BUDGET_USD"]["value"]) > 0
    for name in _SECRETS & env.keys():
        assert env[name] == {"key": name, "sync": False}


def test_render_fixture_text_matches_the_smoke_fixture():
    # The deploy smoke posts invoice_0001 and expects its labelled record back; drift between
    # the descriptor and the fixture would fail the first deploy for no real reason.
    env = {var["key"]: var for var in _render_service()["envVars"]}
    fixture = json.loads(
        (_ROOT / "fixtures" / "invoices" / "invoice_0001.json").read_text(encoding="utf-8")
    )
    assert json.loads(env["FIXTURE_CANNED_TEXT"]["value"]) == fixture["expected"]


def test_railway_runs_exactly_one_replica():
    deploy = _railway()["deploy"]
    assert deploy["numReplicas"] == 1
    assert "multiRegionConfig" not in deploy
    assert deploy["sleepApplication"] is False


def test_both_platforms_probe_a_route_the_app_serves(tmp_path, monkeypatch):
    paths = {_render_service()["healthCheckPath"], _railway()["deploy"]["healthcheckPath"]}
    assert paths == {"/readyz"}
    monkeypatch.setenv("IDEMPOTENCY_DB_PATH", str(tmp_path / "i.sqlite"))
    assert TestClient(create_app()).get("/readyz").status_code == 200
