"""Offline-provider load probe. Windows runs are development checks, not sizing evidence.

Run against fixture mode with invoice_0001 expected JSON as FIXTURE_CANNED_TEXT.
Each level sends the same deterministic round-robin payload mix with fresh keys.
Docker cgroup peak is cumulative since container startup, not a per-level peak;
sampled current usage and CPU capture activity during each level. No paid calls
are configured by this script: the target must be configured separately.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import platform
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pymupdf

# api/content.py's caps, checked against the source by test_load_test.py. Keep
# this runner stdlib + PyMuPDF only, without importing the web application.
_MAX_PDF_BYTES = 10 * 1024 * 1024
_MAX_PDF_PAGES = 1000
_MAX_TEXT_CHARS = 4 * 1024 * 1024

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures/invoices/invoice_0001.json"


@dataclass(frozen=True)
class Payload:
    name: str
    body: bytes
    pdf_bytes: int = 0
    pages: int = 0
    text_chars: int = 0


@dataclass(frozen=True)
class Observation:
    payload: str
    latency_ms: float
    status: int | None
    error_code: str | None = None
    transport_error: str | None = None


def percentile(values: list[float], percent: float) -> float:
    """Linear interpolation at (n - 1) * p, including endpoints."""
    if not values or not 0 <= percent <= 100:
        raise ValueError("percentile needs nonempty values and a percent between 0 and 100")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(observations: list[Observation], elapsed_s: float) -> dict[str, Any]:
    if not observations or elapsed_s <= 0:
        raise ValueError("summary needs observations and positive elapsed seconds")
    latencies = [item.latency_ms for item in observations]
    failures = sum(item.status != 200 for item in observations)
    error_statuses = Counter(str(item.status) for item in observations if item.status != 200)
    error_codes = Counter(item.error_code for item in observations if item.error_code)
    return {
        "requests": len(observations),
        "elapsed_s": elapsed_s,
        "throughput_rps": len(observations) / elapsed_s,
        "successful_rps": (len(observations) - failures) / elapsed_s,
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "p99_ms": percentile(latencies, 99),
        "max_ms": max(latencies),
        "error_rate": failures / len(observations),
        "status_counts": dict(Counter(str(item.status) for item in observations)),
        "error_counts": dict(error_codes),
        "error_rates_by_status": {
            key: count / len(observations) for key, count in error_statuses.items()
        },
        "error_rates_by_code": {
            key: count / len(observations) for key, count in error_codes.items()
        },
        "transport_errors": dict(
            Counter(item.transport_error for item in observations if item.transport_error)
        ),
    }


def generate_pdf(pages: int, *, large: bool = False) -> bytes:
    """Embedded text at about 2 KiB/page, or 4 KiB/page near the three PDF caps.

    Fixed text, layout and PDF IDs make the bytes reproducible. Uncompressed text
    streams model ordinary text PDFs without artificially padding the file.
    """
    if not 1 <= pages < _MAX_PDF_PAGES:
        raise ValueError("synthetic page count must be positive and below the PDF cap")
    lines = 51 if large else 26
    with pymupdf.open() as document:
        for number in range(pages):
            text = "\n".join(
                f"Invoice page {number + 1:04d} line {line + 1:02d}: "
                "Office chairs Northwind Supplies GBP 125.00 quantity 4"
                for line in range(lines)
            )
            page = document.new_page()
            page.insert_text((36, 36), text, fontsize=8)
            # insert_text compresses its streams even when tobytes(deflate=False).
            # Keep ordinary uncompressed text streams to exercise the input cap,
            # rather than filling a tiny compressed PDF with repeated text.
            for xref in page.get_contents():
                document.update_stream(xref, document.xref_stream(xref), compress=False)
        raw: bytes = document.tobytes(no_new_id=True)
    if len(raw) >= _MAX_PDF_BYTES:
        raise ValueError("generated PDF exceeds the input byte cap")
    return raw


def build_payloads() -> list[Payload]:
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    base = {"doc_type": "invoice", "schema_version": "v1", "provider": "default"}
    payloads = [
        Payload("text_invoice", json.dumps({**base, "content": fixture["content"]}).encode())
    ]
    for pages in (1, 10, 50, _MAX_PDF_PAGES - 1):
        raw = generate_pdf(pages, large=pages == _MAX_PDF_PAGES - 1)
        with pymupdf.open(stream=raw, filetype="pdf") as document:
            text_chars = sum(len(page.get_text()) for page in document) + pages - 1
        if text_chars >= _MAX_TEXT_CHARS:
            raise ValueError("generated PDF exceeds the extracted text cap")
        payloads.append(
            Payload(
                f"pdf_{pages}_pages",
                json.dumps(
                    {
                        **base,
                        "content_format": "pdf_base64",
                        "content": base64.b64encode(raw).decode(),
                    }
                ).encode(),
                len(raw),
                pages,
                text_chars,
            )
        )
    return payloads


def send_request(base_url: str, payload: Payload, key: str, timeout: float) -> Observation:
    request = Request(
        f"{base_url.rstrip('/')}/v1/extract",
        data=payload.body,
        headers={"Content-Type": "application/json", "Idempotency-Key": key},
        method="POST",
    )
    started = time.perf_counter()
    error_code = None
    try:
        try:
            with urlopen(request, timeout=timeout) as response:
                status = response.status
                body = response.read()
        except HTTPError as exc:
            status = exc.code
            body = exc.read()
        if status != 200:
            try:
                decoded = json.loads(body)
            except (ValueError, UnicodeDecodeError):
                decoded = None
            if isinstance(decoded, dict) and isinstance(decoded.get("error"), str):
                error_code = decoded["error"]
        return Observation(payload.name, (time.perf_counter() - started) * 1000, status, error_code)
    except (URLError, OSError, HTTPException) as exc:
        return Observation(
            payload.name,
            (time.perf_counter() - started) * 1000,
            None,
            transport_error=type(exc).__name__,
        )


def _docker(*arguments: str) -> str:
    return subprocess.run(
        ["docker", *arguments], check=True, capture_output=True, text=True, timeout=15
    ).stdout.strip()


def docker_sample(container: str) -> dict[str, Any]:
    """Retain sampling errors explicitly, including stopped/OOM-killed containers."""
    sample: dict[str, Any] = {"time_epoch": time.time()}
    try:
        stats = json.loads(_docker("stats", "--no-stream", "--format", "{{json .}}", container))
        sample["memory_usage"] = stats["MemUsage"]
        sample["cpu_percent"] = float(stats["CPUPerc"].rstrip("%"))
        for version, path in (
            ("v2", "/sys/fs/cgroup/memory.peak"),
            ("v1", "/sys/fs/cgroup/memory/memory.max_usage_in_bytes"),
        ):
            try:
                sample["container_lifetime_peak_bytes"] = int(
                    _docker("exec", container, "cat", path)
                )
                sample["cgroup_version"] = version
                break
            except subprocess.CalledProcessError:
                continue
        else:
            sample["peak_error"] = "neither cgroup peak counter is readable"
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        sample["sample_error"] = str(exc)
    return sample


def container_state(container: str) -> dict[str, Any]:
    try:
        state: dict[str, Any] = json.loads(
            _docker("inspect", "--format", "{{json .State}}", container)
        )
        return state
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {"inspect_error": str(exc)}


def run_level(
    base_url: str,
    payloads: list[Payload],
    level: int,
    requests: int,
    timeout: float,
    container: str | None,
) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    stop = threading.Event()

    def sample_memory() -> None:
        assert container is not None
        while not stop.is_set():
            samples.append(docker_sample(container))
            stop.wait(1)

    sampler = threading.Thread(target=sample_memory) if container else None
    if sampler:
        sampler.start()
    run_id = uuid.uuid4().hex
    started = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=level) as pool:
            futures = [
                pool.submit(
                    send_request,
                    base_url,
                    payloads[index % len(payloads)],
                    f"load-{run_id}-{index}",
                    timeout,
                )
                for index in range(requests)
            ]
            observations = [future.result() for future in futures]
        elapsed = time.perf_counter() - started
    finally:
        stop.set()
        if sampler:
            sampler.join()
    if container:
        samples.append(docker_sample(container))
    return {
        "concurrency": level,
        **summarize(observations, elapsed),
        "observations": [asdict(item) for item in observations],
        "docker_samples": samples,
    }


def markdown_table(results: list[dict[str, Any]]) -> str:
    lines = [
        "| Concurrency | req/s | p50 ms | p95 ms | p99 ms | max ms | Errors | "
        "Lifetime peak MiB | Current memory | CPU % |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for result in results:
        samples = result["docker_samples"]
        peaks = [
            s["container_lifetime_peak_bytes"]
            for s in samples
            if "container_lifetime_peak_bytes" in s
        ]
        currents = [s["memory_usage"] for s in samples if "memory_usage" in s]
        cpus = [s["cpu_percent"] for s in samples if "cpu_percent" in s]
        peak = f"{max(peaks) / 1024**2:.1f}" if peaks else "n/a"
        cpu = f"{max(cpus):.1f}" if cpus else "n/a"
        current = currents[-1] if currents else "n/a"
        lines.append(
            f"| {result['concurrency']} | {result['throughput_rps']:.2f} | "
            f"{result['p50_ms']:.1f} | {result['p95_ms']:.1f} | {result['p99_ms']:.1f} | "
            f"{result['max_ms']:.1f} | {result['error_rate']:.1%} | {peak} | {current} | {cpu} |"
        )
    return "\n".join(lines) + "\n"


def positive_int(raw: str) -> int:
    if not raw.isascii() or not raw.isdecimal() or int(raw) <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return int(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8200")
    parser.add_argument("--container")
    parser.add_argument("--levels", default="1,2,4,8,16,32")
    parser.add_argument("--requests", type=positive_int, default=40)
    parser.add_argument(
        "--timeout", type=positive_int, default=120, help="request timeout in seconds"
    )
    parser.add_argument("--out-dir", type=Path, default=Path("loadtest-results"))
    parser.add_argument("--smoke", action="store_true", help="one level, three requests")
    args = parser.parse_args()
    try:
        levels = [positive_int(raw) for raw in args.levels.split(",")]
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    if args.smoke:
        levels = levels[:1]
        args.requests = 3
    payloads = build_payloads()
    results: list[dict[str, Any]] = []
    args.out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "base_url": args.base_url,
        "container": args.container,
        "percentile_method": "linear interpolation at (n - 1) * p",
        "memory_note": "cgroup peak is cumulative since container startup; CPU is sampled maximum",
        "payloads": [
            {
                "name": p.name,
                "request_bytes": len(p.body),
                "pdf_bytes": p.pdf_bytes,
                "pages": p.pages,
                "text_chars": p.text_chars,
            }
            for p in payloads
        ],
        "levels": results,
    }
    for level in levels:
        result = run_level(
            args.base_url, payloads, level, args.requests, args.timeout, args.container
        )
        results.append(result)
        if args.container:
            report["container_state"] = container_state(args.container)
        # Checkpoint each level so a subsequent OOM or job timeout retains evidence.
        (args.out_dir / "results.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        (args.out_dir / "results.md").write_text(markdown_table(results), encoding="utf-8")
        print(markdown_table([result]), flush=True)
        if args.container and report["container_state"].get("OOMKilled"):
            break
    return int(any(result["error_rate"] for result in results))


if __name__ == "__main__":
    sys.exit(main())
