"""Accuracy harness orchestration (T16): REVIEWED-only loading, injected-predictor scoring,
the live predictor (mocked httpx), and the CLI exit paths. All offline."""

from __future__ import annotations

import json

import httpx
import pytest

from harness.run_accuracy import live_predictor, load_reviewed_fixtures, main, run_accuracy

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


class _FakeResp:
    def __init__(self, data: dict[str, object], cost: float, latency: float) -> None:
        self._body = {"data": data, "meta": {"cost_usd": cost, "latency_ms": latency}}

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, object]:
        return self._body


def test_load_reviewed_fixtures_excludes_draft(tmp_path):
    inv = tmp_path / "invoices"
    _write(inv, "a.json", "REVIEWED")
    _write(inv, "b.json", "DRAFT")
    loaded = load_reviewed_fixtures("invoice", root=tmp_path)
    assert len(loaded) == 1
    assert loaded[0]["label_status"] == "REVIEWED"


def test_run_accuracy_perfect_predictor_is_100pct():
    fixtures = [{"doc_type": "invoice", "schema_version": "v1", "content": "x", "expected": _BASE}]
    report = run_accuracy(
        "invoice", "openai", lambda fx: (fx["expected"], 0.01, 5.0), fixtures=fixtures
    )
    assert report.n_fixtures == 1
    assert report.overall_exact_match_rate == 1.0
    assert report.cost_usd_total == pytest.approx(0.01)


def test_run_accuracy_counts_a_mismatch():
    fixtures = [{"doc_type": "invoice", "schema_version": "v1", "content": "x", "expected": _BASE}]

    def predict(fx):
        return ({**fx["expected"], "invoice_number": "WRONG"}, 0.0, 1.0)

    report = run_accuracy("invoice", "openai", predict, fixtures=fixtures)
    assert report.per_field["invoice_number"].mismatches == 1
    assert report.overall_exact_match_rate < 1.0


def test_live_predictor_posts_and_parses(monkeypatch):
    captured: dict[str, object] = {}

    def fake_post(url, *, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _FakeResp(_BASE, 0.5, 99.0)

    monkeypatch.setattr(httpx, "post", fake_post)
    predict = live_predictor("http://host:8200/", "anthropic")
    data, cost, latency = predict(
        {"doc_type": "invoice", "schema_version": "v1", "content": "c", "expected": _BASE}
    )
    assert captured["url"] == "http://host:8200/v1/extract"  # trailing slash trimmed
    assert captured["json"]["provider"] == "anthropic"
    assert data == _BASE
    assert (cost, latency) == (0.5, 99.0)


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
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResp(_BASE, 0.01, 12.0))
    out = tmp_path / "report.md"
    assert main(["--doc-type", "invoice", "--live", "--out", str(out)]) == 0
    assert "### invoice / openai" in capsys.readouterr().out
    assert out.exists()
    assert "overall exact-match: 100.0%" in out.read_text(encoding="utf-8")
