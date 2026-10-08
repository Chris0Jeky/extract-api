"""Load probe math and real synthetic PDF decoding, without a running server."""

import base64
import json
import subprocess
from urllib.error import HTTPError, URLError

import pytest
from scripts import load_test
from scripts.load_test import Observation, build_payloads, generate_pdf, percentile, summarize

from api.content import _MAX_PDF_BYTES, _MAX_PDF_PAGES, _MAX_TEXT_CHARS, extract_pdf_text
from api.models import ExtractRequest


@pytest.mark.parametrize(
    "values, percent, expected",
    [
        ([10], 99, 10),
        ([40, 10, 30, 20], 50, 25),
        ([10, 20, 30, 40], 95, 38.5),
        ([10, 20, 30, 40], 99, 39.7),
        ([2, 1], 0, 1),
        ([2, 1], 100, 2),
    ],
)
def test_percentile_interpolation(values, percent, expected):
    assert percentile(values, percent) == pytest.approx(expected)


@pytest.mark.parametrize("values, percent", [([], 50), ([1], -1), ([1], 101)])
def test_percentile_rejects_invalid_input(values, percent):
    with pytest.raises(ValueError):
        percentile(values, percent)


def test_summary_counts_latency_success_and_each_error_kind():
    results = [
        Observation("text", 100, 200),
        Observation("pdf", 200, 422, "validation_failed"),
        Observation("text", 300, 502, "provider_error"),
        Observation("pdf", 400, None, transport_error="URLError"),
    ]
    summary = summarize(results, 2)
    assert summary["throughput_rps"] == 2
    assert summary["successful_rps"] == 0.5
    assert summary["error_rate"] == 0.75
    assert summary["status_counts"] == {"200": 1, "422": 1, "502": 1, "None": 1}
    assert summary["error_counts"] == {"validation_failed": 1, "provider_error": 1}
    assert summary["error_rates_by_status"] == {"422": 0.25, "502": 0.25, "None": 0.25}
    assert summary["error_rates_by_code"] == {"validation_failed": 0.25, "provider_error": 0.25}
    assert summary["transport_errors"] == {"URLError": 1}
    assert summary["p50_ms"] == 250
    assert summary["p95_ms"] == pytest.approx(385)
    assert summary["p99_ms"] == pytest.approx(397)
    assert summary["max_ms"] == 400


def test_all_success_summary_and_empty_summary():
    assert summarize([Observation("text", 10, 200)], 1)["error_rate"] == 0
    for results, elapsed in [([], 1), ([Observation("text", 10, 200)], 0)]:
        with pytest.raises(ValueError):
            summarize(results, elapsed)


def test_pdf_mix_has_real_text_and_stays_below_caps():
    assert load_test._MAX_PDF_BYTES == _MAX_PDF_BYTES
    assert load_test._MAX_PDF_PAGES == _MAX_PDF_PAGES
    assert load_test._MAX_TEXT_CHARS == _MAX_TEXT_CHARS
    payloads = build_payloads()
    assert [p.pages for p in payloads] == [0, 1, 10, 50, _MAX_PDF_PAGES - 1]
    for payload in payloads:
        request = ExtractRequest.model_validate_json(payload.body)
        if payload.pages:
            assert len(base64.b64decode(request.content)) == payload.pdf_bytes < _MAX_PDF_BYTES
            text = extract_pdf_text(request.content)
            assert 0 < len(text) == payload.text_chars < _MAX_TEXT_CHARS
            assert "Office chairs" in text
    assert 1900 < payloads[1].text_chars < 2300
    assert payloads[-1].text_chars > 0.95 * _MAX_TEXT_CHARS
    assert payloads[-1].pdf_bytes > 0.75 * _MAX_PDF_BYTES


def test_pdf_is_deterministic_and_rejects_bad_page_counts():
    assert generate_pdf(1) == generate_pdf(1)
    for pages in (0, _MAX_PDF_PAGES):
        with pytest.raises(ValueError):
            generate_pdf(pages)


def test_http_taxonomy_and_transport_errors(monkeypatch):
    from io import BytesIO

    payload = load_test.Payload("text", b"{}")

    def http_error(*args, **kwargs):
        raise HTTPError("http://test", 422, "bad", {}, BytesIO(b'{"error":"validation_failed"}'))

    monkeypatch.setattr(load_test, "urlopen", http_error)
    observed = load_test.send_request("http://test", payload, "unique", 1)
    assert observed.status == 422
    assert observed.error_code == "validation_failed"

    def transport_error(*args, **kwargs):
        raise URLError("connection refused")

    monkeypatch.setattr(load_test, "urlopen", transport_error)
    observed = load_test.send_request("http://test", payload, "unique", 1)
    assert observed.status is None and observed.transport_error == "URLError"


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_docker_memory_peak_fallback_and_cpu(monkeypatch, version):
    def docker(*args):
        if args[0] == "stats":
            return json.dumps({"MemUsage": "200MiB / 512MiB", "CPUPerc": "49.50%"})
        if version == "v1" and args[-1] == "/sys/fs/cgroup/memory.peak":
            raise subprocess.CalledProcessError(1, "docker")
        return "314572800"

    monkeypatch.setattr(load_test, "_docker", docker)
    sample = load_test.docker_sample("test")
    assert sample["cgroup_version"] == version
    assert sample["container_lifetime_peak_bytes"] == 300 * 1024**2
    assert sample["cpu_percent"] == 49.5
    assert sample["memory_usage"] == "200MiB / 512MiB"


def test_smoke_writes_results_and_uses_three_fresh_keys(monkeypatch, tmp_path):
    keys = []

    def send(base_url, payload, key, timeout):
        keys.append(key)
        return Observation(payload.name, 10, 200)

    monkeypatch.setattr(load_test, "send_request", send)
    monkeypatch.setattr(load_test, "build_payloads", lambda: [load_test.Payload("text", b"{}")])
    monkeypatch.setattr(
        load_test.sys, "argv", ["load_test.py", "--smoke", "--out-dir", str(tmp_path)]
    )
    assert load_test.main() == 0
    assert len(keys) == len(set(keys)) == 3
    report = json.loads((tmp_path / "results.json").read_text())
    assert len(report["levels"]) == 1
    assert report["levels"][0]["requests"] == 3
    assert "| 1 |" in (tmp_path / "results.md").read_text()
