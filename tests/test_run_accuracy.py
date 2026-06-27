"""Accuracy harness orchestration (T16): REVIEWED-only loading, injected-predictor scoring,
the failed-extraction path, the live predictor (mocked httpx), and the CLI exit paths.
All offline."""

from __future__ import annotations

import json

import httpx
import pytest

from harness.run_accuracy import (
    Prediction,
    PredictionFailed,
    live_predictor,
    load_reviewed_fixtures,
    main,
    run_accuracy,
)

_BASE: dict[str, object] = {
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


def _fixture(content: str = "x") -> dict[str, object]:
    return {"doc_type": "invoice", "schema_version": "v1", "content": content, "expected": _BASE}


def _write(directory, name: str, status: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(
        json.dumps(
            {
                "fixture_id": name,
                "doc_type": "invoice",
                "schema_version": "v1",
                "label_status": status,
                "content": "doc text",
                "expected": _BASE,
            }
        ),
        encoding="utf-8",
    )


def _resp(status: int, body: dict[str, object]) -> httpx.Response:
    # A real httpx.Response so raise_for_status() behaves authentically (raises on >= 400).
    return httpx.Response(status, request=httpx.Request("POST", "http://x/v1/extract"), json=body)


def _ok_body(
    provider: str = "openai", cost: float = 0.01, latency: float = 12.0
) -> dict[str, object]:
    return {"data": _BASE, "meta": {"cost_usd": cost, "latency_ms": latency, "provider": provider}}


def test_load_reviewed_fixtures_excludes_draft(tmp_path):
    inv = tmp_path / "invoices"
    _write(inv, "a.json", "REVIEWED")
    _write(inv, "b.json", "DRAFT")
    loaded = load_reviewed_fixtures("invoice", root=tmp_path)
    assert len(loaded) == 1
    assert loaded[0]["label_status"] == "REVIEWED"


def test_run_accuracy_perfect_predictor_is_100pct():
    report = run_accuracy(
        "invoice",
        "openai",
        lambda fx: Prediction(fx["expected"], 0.01, 5.0, "openai"),
        fixtures=[_fixture()],
    )
    assert report.n_fixtures == 1
    assert report.n_failures == 0
    assert report.overall_exact_match_rate == 1.0
    assert report.cost_usd_total == pytest.approx(0.01)


def test_run_accuracy_counts_a_mismatch():
    def predict(fx):
        return Prediction({**fx["expected"], "invoice_number": "WRONG"}, 0.0, 1.0, "openai")

    report = run_accuracy("invoice", "openai", predict, fixtures=[_fixture()])
    assert report.per_field["invoice_number"].mismatches == 1
    assert report.overall_exact_match_rate < 1.0


def test_run_accuracy_records_a_failed_extraction_and_continues():
    fixtures = [_fixture("a"), _fixture("b")]
    seen = {"n": 0}

    def predict(fx):
        seen["n"] += 1
        if seen["n"] == 1:
            raise PredictionFailed("first fixture failed")
        return Prediction(fx["expected"], 0.02, 8.0, "openai")

    report = run_accuracy("invoice", "openai", predict, fixtures=fixtures)
    assert report.n_fixtures == 2  # both fixtures recorded (the run did not abort)
    assert report.n_failures == 1
    # the failed fixture's present fields counted as missed, so overall is below 100%
    assert 0.0 < report.overall_exact_match_rate < 1.0
    assert report.cost_usd_total == pytest.approx(0.02)  # only the successful call's cost


def test_run_accuracy_labels_report_with_server_resolved_provider():
    # Requested "default", but the server resolved "anthropic"; the report reflects reality.
    report = run_accuracy(
        "invoice",
        "default",
        lambda fx: Prediction(fx["expected"], 0.0, 1.0, "anthropic"),
        fixtures=[_fixture()],
    )
    assert report.provider == "anthropic"


def test_live_predictor_posts_and_parses(monkeypatch):
    captured: dict[str, object] = {}

    def fake_post(url, *, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _resp(200, _ok_body(provider="openai", cost=0.5, latency=99.0))

    monkeypatch.setattr(httpx, "post", fake_post)
    pred = live_predictor("http://host:8200/", "anthropic")(_fixture("c"))
    assert captured["url"] == "http://host:8200/v1/extract"  # trailing slash trimmed
    assert captured["json"]["provider"] == "anthropic"  # the requested provider is sent
    assert pred.record == _BASE
    assert (pred.cost_usd, pred.latency_ms) == (0.5, 99.0)
    assert pred.provider == "openai"  # server-resolved, read from meta


def test_live_predictor_non_2xx_raises_prediction_failed(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(422, {"error": "validation_failed"}))
    with pytest.raises(PredictionFailed):
        live_predictor("http://h", "openai")({**_fixture("c"), "fixture_id": "f1"})


def test_live_predictor_transport_error_raises_prediction_failed(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(PredictionFailed):
        live_predictor("http://h", "openai")(_fixture("c"))


def test_main_no_reviewed_fixtures_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("harness.run_accuracy._FIXTURES_ROOT", tmp_path)
    _write(tmp_path / "invoices", "a.json", "DRAFT")  # only DRAFT -> nothing to score
    assert main(["--doc-type", "invoice"]) == 1
    assert "no REVIEWED" in capsys.readouterr().err


def test_main_without_live_explains_and_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("harness.run_accuracy._FIXTURES_ROOT", tmp_path)
    _write(tmp_path / "invoices", "a.json", "REVIEWED")
    assert main(["--doc-type", "invoice"]) == 2
    assert "--live" in capsys.readouterr().err


def test_main_live_renders_and_writes_report(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("harness.run_accuracy._FIXTURES_ROOT", tmp_path)
    _write(tmp_path / "invoices", "a.json", "REVIEWED")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(200, _ok_body()))
    out = tmp_path / "report.md"
    assert main(["--doc-type", "invoice", "--live", "--out", str(out)]) == 0
    assert "### invoice / openai" in capsys.readouterr().out
    assert out.exists()
    assert "overall exact-match: 100.0%" in out.read_text(encoding="utf-8")
