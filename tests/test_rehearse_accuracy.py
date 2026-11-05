"""The offline rehearsal exercises real endpoint validation without provider traffic."""

import json
import os
from pathlib import Path

import pytest
from scripts.rehearse_accuracy import main, rehearse

ROOT = Path(__file__).resolve().parent.parent


def _corpus(tmp_path):
    folder = tmp_path / "invoices"
    folder.mkdir()
    source = ROOT / "fixtures" / "invoices"
    for name in ("invoice_0001.json", "invoice_0002.json"):
        (folder / name).write_text((source / name).read_text(), encoding="utf-8")
    draft = json.loads((source / "invoice_0001.json").read_text())
    draft.update(fixture_id="draft", label_status="DRAFT", expected={})
    (folder / "draft.json").write_text(json.dumps(draft), encoding="utf-8")
    return tmp_path


def test_rehearsal_echoes_each_reviewed_fixture_through_api(tmp_path, monkeypatch):
    import llm.client

    def no_paid_client(*args, **kwargs):
        pytest.fail("offline rehearsal constructed a paid provider client")

    monkeypatch.setattr(llm.client, "OpenAIClient", no_paid_client)
    monkeypatch.setattr(llm.client, "AnthropicClient", no_paid_client)
    monkeypatch.setenv("LLM_PROVIDER_MODE", "live")
    monkeypatch.setenv("FIXTURE_CANNED_TEXT", "original value")
    monkeypatch.setenv("FIXTURE_LATENCY_MS", "invalid ambient value")
    before = dict(os.environ)
    report = rehearse("invoice", fixtures_root=_corpus(tmp_path))
    assert report.provider == "fixture"
    assert report.n_fixtures == 2
    assert report.n_failures == report.n_skipped == 0
    assert report.overall_exact_match_rate == 1.0
    assert report.cost_usd_total == 0.0
    assert dict(os.environ) == before


def test_rehearsal_does_not_replace_endpoint_with_label_echo(tmp_path, monkeypatch):
    from fastapi import Response

    import api.main

    real_create_app = api.main.create_app

    def broken_app(**kwargs):
        app = real_create_app(**kwargs)

        @app.middleware("http")
        async def refuse(request, call_next):
            return Response(status_code=503)

        return app

    monkeypatch.setattr(api.main, "create_app", broken_app)
    report = rehearse("invoice", fixtures_root=_corpus(tmp_path))
    assert report.n_failures == 2
    assert report.overall_exact_match_rate == 0.0


def test_rehearsal_refuses_empty_reviewed_corpus(tmp_path):
    with pytest.raises(ValueError, match="no REVIEWED"):
        rehearse("uk_job_posting", fixtures_root=tmp_path)


def test_rehearsal_cli_labels_report_as_not_provider_evidence(tmp_path, capsys):
    result = main(["--doc-type", "invoice", "--fixtures-root", str(_corpus(tmp_path))])
    captured = capsys.readouterr()
    assert result == 0
    assert "OFFLINE REHEARSAL" in captured.out
    assert "not provider accuracy" in captured.out
    assert "invoice / fixture" in captured.out
    assert "$0.0000" in captured.out


def test_rehearsal_cli_fails_loud_for_empty_corpus(tmp_path, capsys):
    assert main(["--doc-type", "uk_job_posting", "--fixtures-root", str(tmp_path)]) == 1
    assert "no REVIEWED" in capsys.readouterr().err


def test_rehearsal_restores_environment_after_invalid_label(tmp_path, monkeypatch):
    root = _corpus(tmp_path)
    path = root / "invoices" / "invoice_0002.json"
    data = json.loads(path.read_text())
    data["expected"] = {}
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.delenv("FIXTURE_CANNED_TEXT", raising=False)
    before = dict(os.environ)
    with pytest.raises(ValueError, match="expected label"):
        rehearse("invoice", fixtures_root=root)
    assert dict(os.environ) == before
