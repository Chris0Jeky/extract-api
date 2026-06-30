"""Accuracy harness orchestration (T16): REVIEWED-only loading, injected-predictor scoring,
the failed-extraction path, the live predictor (mocked httpx), and the CLI exit paths.
All offline."""

from __future__ import annotations

import json

import httpx
import pytest

from harness.run_accuracy import (
    ControlPlaneRejection,
    MisplacedFixture,
    Prediction,
    PredictionFailed,
    _response_error_code,
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


def _write(directory, name: str, status: str, doc_type: str = "invoice") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(
        json.dumps(
            {
                "fixture_id": name,
                "doc_type": doc_type,
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


def test_run_accuracy_skips_control_plane_rejection_out_of_denominator():
    # A budget/idempotency rejection never reached the model, so the fixture is skipped, NOT
    # scored as all-missed; it must not appear in the per-field denominator (issue #52).
    fixtures = [_fixture("a"), _fixture("b")]
    seen = {"n": 0}

    def predict(fx):
        seen["n"] += 1
        if seen["n"] == 1:
            raise ControlPlaneRejection("budget exhausted")
        return Prediction(fx["expected"], 0.02, 8.0, "openai")

    report = run_accuracy("invoice", "openai", predict, fixtures=fixtures)
    assert report.n_skipped == 1
    assert report.n_failures == 0
    assert report.n_fixtures == 1  # only the scored fixture is in the denominator
    assert report.overall_exact_match_rate == 1.0  # the one scored fixture was perfect
    assert report.cost_usd_total == pytest.approx(0.02)  # the skipped fixture contributes no cost


def test_run_accuracy_skip_is_distinct_from_failure():
    # success scored, a quality failure scored as all-missed, a control-plane rejection skipped.
    fixtures = [_fixture("a"), _fixture("b"), _fixture("c")]
    seen = {"n": 0}

    def predict(fx):
        seen["n"] += 1
        if seen["n"] == 2:
            raise PredictionFailed("provider_error")
        if seen["n"] == 3:
            raise ControlPlaneRejection("budget exhausted")
        return Prediction(fx["expected"], 0.05, 8.0, "openai")

    report = run_accuracy("invoice", "openai", predict, fixtures=fixtures)
    assert (report.n_failures, report.n_skipped) == (1, 1)
    assert report.n_fixtures == 2  # success + failure scored; the skip is excluded
    assert 0.0 < report.overall_exact_match_rate < 1.0


def test_run_accuracy_all_fixtures_skipped_scores_nothing():
    # If every fixture is a control-plane rejection (e.g. a budget cap set below corpus cost),
    # the run scores nothing rather than reporting a misleading all-missed corpus (issue #52).
    def predict(fx):
        raise ControlPlaneRejection("budget exhausted")

    report = run_accuracy("invoice", "openai", predict, fixtures=[_fixture("a"), _fixture("b")])
    assert report.n_skipped == 2
    assert report.n_fixtures == 0
    assert report.total_fields == 0
    assert report.overall_exact_match_rate == 0.0  # the 0/0 property guard holds


def test_run_accuracy_schema_invalid_prediction_is_a_failure():
    # A 200 with object-but-schema-invalid data ({}) must be a failed extraction, not a crash
    # in score_record's strict canonicalization (issue #57, codex review).
    report = run_accuracy(
        "invoice",
        "openai",
        lambda fx: Prediction({}, 0.01, 5.0, "openai"),  # {} is not a valid invoice record
        fixtures=[_fixture()],
    )
    assert report.n_failures == 1
    assert report.n_fixtures == 1
    assert report.overall_exact_match_rate == 0.0  # scored as all-missed, run did not crash


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


@pytest.mark.parametrize(
    ("status", "code"),
    [(402, "budget_exceeded"), (409, "idempotency_conflict")],
)
def test_live_predictor_control_plane_rejection_is_skipped(monkeypatch, status, code):
    # A coded control-plane non-2xx is a ControlPlaneRejection (skipped), not a quality failure.
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(status, {"error": code}))
    with pytest.raises(ControlPlaneRejection):
        live_predictor("http://h", "openai")({**_fixture("c"), "fixture_id": "f1"})


def test_live_predictor_unclassifiable_4xx_is_a_quality_failure(monkeypatch):
    # A 402 whose body carries no recognizable control-plane code is treated as a failure, not
    # silently skipped: we only skip what we can positively classify as control-plane (#52).
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(402, {"error": "mystery"}))
    with pytest.raises(PredictionFailed):
        live_predictor("http://h", "openai")(_fixture("c"))


def test_response_error_code_reads_taxonomy_code():
    assert _response_error_code(_resp(402, {"error": "budget_exceeded"})) == "budget_exceeded"


def test_response_error_code_none_for_non_dict_or_uncoded_body():
    assert _response_error_code(_resp(402, {})) is None  # no `error` key
    assert _response_error_code(_resp(402, ["budget_exceeded"])) is None  # not an object
    # A non-JSON body (e.g. a gateway HTML page) yields None rather than raising.
    html = httpx.Response(402, request=httpx.Request("POST", "http://x"), text="<html>nope</html>")
    assert _response_error_code(html) is None


# --- issue #57: --live robustness (malformed 2xx, configurable timeout, misplaced fixtures) ---


def test_live_predictor_malformed_2xx_missing_keys_is_failure(monkeypatch):
    # A 200 that is not a valid ExtractResponse (missing data/meta) is a fixture failure,
    # not an uncaught KeyError that aborts the whole run (issue #57).
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(200, {"unexpected": "shape"}))
    with pytest.raises(PredictionFailed):
        live_predictor("http://h", "openai")({**_fixture("c"), "fixture_id": "f1"})


def test_live_predictor_non_json_2xx_is_failure(monkeypatch):
    # A 200 whose body is not JSON (a gateway login/HTML page) is a fixture failure, not a crash.
    html = httpx.Response(
        200, request=httpx.Request("POST", "http://x/v1/extract"), text="<html>login</html>"
    )
    monkeypatch.setattr(httpx, "post", lambda *a, **k: html)
    with pytest.raises(PredictionFailed):
        live_predictor("http://h", "openai")(_fixture("c"))


def test_live_predictor_2xx_data_not_object_is_failure(monkeypatch):
    # A 200 whose `data` is not a JSON object would break scoring downstream; fail the fixture.
    body = {"data": "not-an-object", "meta": _ok_body()["meta"]}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(200, body))
    with pytest.raises(PredictionFailed):
        live_predictor("http://h", "openai")(_fixture("c"))


def test_live_predictor_2xx_overflowing_numeric_is_failure(monkeypatch):
    # float() of an out-of-range JSON integer raises OverflowError (an ArithmeticError, not a
    # ValueError); it must still degrade to a fixture failure, not crash the run (issue #57).
    body = {"data": _BASE, "meta": {"cost_usd": 10**400, "latency_ms": 1.0, "provider": "openai"}}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(200, body))
    with pytest.raises(PredictionFailed):
        live_predictor("http://h", "openai")(_fixture("c"))


@pytest.mark.parametrize("over", [{"cost_usd": "nan"}, {"latency_ms": "inf"}, {"cost_usd": "-inf"}])
def test_live_predictor_non_finite_metric_is_failure(monkeypatch, over):
    # float("nan")/float("inf") parse without error, so a non-finite 2xx metric would silently
    # poison the cost total / latency percentiles; it must be a fixture failure (issue #57, codex).
    meta = {"cost_usd": 0.01, "latency_ms": 1.0, "provider": "openai", **over}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(200, {"data": _BASE, "meta": meta}))
    with pytest.raises(PredictionFailed):
        live_predictor("http://h", "openai")(_fixture("c"))


def test_live_predictor_respects_configurable_timeout(monkeypatch):
    captured: dict[str, object] = {}

    def fake_post(url, *, json, timeout):
        captured["timeout"] = timeout
        return _resp(200, _ok_body())

    monkeypatch.setattr(httpx, "post", fake_post)
    live_predictor("http://h", "openai", timeout=7.5)(_fixture("c"))
    assert captured["timeout"] == 7.5  # the configured timeout is passed through, not a fixed 120


def test_load_reviewed_fixtures_fails_loud_on_misplaced_reviewed(tmp_path):
    # A REVIEWED fixture filed under the wrong doc-type directory is a loud setup error.
    inv = tmp_path / "invoices"
    _write(inv, "ok.json", "REVIEWED")
    _write(inv, "wrong.json", "REVIEWED", doc_type="uk_job_posting")
    with pytest.raises(MisplacedFixture) as exc:
        load_reviewed_fixtures("invoice", root=tmp_path)
    assert "wrong.json" in str(exc.value)


def test_load_reviewed_fixtures_fails_loud_on_non_object_fixture(tmp_path):
    # A fixture file that is a JSON array/primitive (not an object) is a loud setup error,
    # not a cryptic AttributeError from data.get().
    inv = tmp_path / "invoices"
    inv.mkdir(parents=True, exist_ok=True)
    (inv / "bad.json").write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        load_reviewed_fixtures("invoice", root=tmp_path)


def test_load_reviewed_fixtures_ignores_misplaced_draft(tmp_path):
    # A DRAFT with the wrong doc_type is never scored anyway, so it is excluded, not an error.
    inv = tmp_path / "invoices"
    _write(inv, "ok.json", "REVIEWED")
    _write(inv, "amisplaceddraft.json", "DRAFT", doc_type="uk_job_posting")
    loaded = load_reviewed_fixtures("invoice", root=tmp_path)
    assert [d["fixture_id"] for d in loaded] == ["ok.json"]


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


@pytest.mark.parametrize("bad", ["0", "-5", "nan", "inf"])
def test_main_rejects_non_positive_or_non_finite_timeout(bad):
    # A non-positive OR non-finite --live timeout is nonsensical; fail loud rather than let it
    # reach httpx (NaN slips past a bare `<= 0` guard, inf means no effective timeout).
    with pytest.raises(SystemExit):
        main(["--doc-type", "invoice", "--live", "--timeout", bad])


def test_main_live_passes_timeout_through(tmp_path, monkeypatch):
    monkeypatch.setattr("harness.run_accuracy._FIXTURES_ROOT", tmp_path)
    _write(tmp_path / "invoices", "a.json", "REVIEWED")
    captured: dict[str, object] = {}

    def fake_post(url, *, json, timeout):
        captured["timeout"] = timeout
        return _resp(200, _ok_body())

    monkeypatch.setattr(httpx, "post", fake_post)
    assert main(["--doc-type", "invoice", "--live", "--timeout", "33"]) == 0
    assert captured["timeout"] == 33.0  # the CLI flag reaches the HTTP client
