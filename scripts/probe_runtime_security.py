#!/usr/bin/env python3
"""Report two tracked CPython behaviors using synthetic in-memory inputs only.

This is applicability evidence for issue #194, not a vulnerability scanner or a
replacement for Grype. A finding is report-only; a broken probe exits nonzero.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import io
import json
import platform
import poplib
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, cast


@dataclass(frozen=True)
class Case:
    name: str
    kind: Literal["control", "regression"]
    outcome: Literal["expected", "unexpected", "error"]
    observation: str


def check_status(cases: list[Case]) -> str:
    if {case.kind for case in cases} != {"control", "regression"} or any(
        case.outcome == "error" or (case.kind == "control" and case.outcome != "expected")
        for case in cases
    ):
        return "inconclusive"
    if any(case.outcome == "unexpected" for case in cases):
        return "affected_behavior_observed"
    return "affected_behavior_not_observed"


class _CapturePOP3(poplib.POP3):
    """Exercise the installed command formatter without connecting to a server."""

    def __init__(self) -> None:
        self._debugging = 0
        self.encoding = "utf-8"
        self.sent: list[bytes] = []

    def _putline(self, line: bytes) -> None:
        self.sent.append(line)

    def _getresp(self) -> bytes:
        return b"+OK synthetic"


def probe_poplib() -> list[Case]:
    cases = []
    for method in ("user", "pass_"):
        for code in (None, *range(32), 127):
            client = _CapturePOP3()
            value = "synthetic" if code is None else f"synthetic{chr(code)}value"
            kind: Literal["control", "regression"] = "control" if code is None else "regression"
            name = f"{method}_{'valid' if code is None else f'control_{code:02x}'}"
            try:
                getattr(client, method)(value)
                rejected = False
            except ValueError:
                rejected = True
            except Exception as exc:
                cases.append(Case(name, kind, "error", type(exc).__name__))
                continue
            if code is None:
                okay = not rejected and len(client.sent) == 1
            else:
                okay = rejected and not client.sent
            observation = (
                "sent" if client.sent else ("rejected before send" if rejected else "no send")
            )
            cases.append(Case(name, kind, "expected" if okay else "unexpected", observation))
    return cases


class _HTTPInput:
    def __init__(self, response: bytes) -> None:
        self.response = response

    def makefile(self, mode: str) -> io.BytesIO:
        return io.BytesIO(self.response)


def _content_length_case(value: str, *, valid: bool) -> Case:
    kind: Literal["control", "regression"] = "control" if valid else "regression"
    name = f"content_length_{value!r}"
    wire = f"HTTP/1.1 200 OK\r\nContent-Length: {value}\r\n\r\nHello\r\nextra".encode("ascii")
    try:
        with http.client.HTTPResponse(cast(Any, _HTTPInput(wire)), method="GET") as response:
            response.begin()
            length = response.length
            okay = (length == 7 and response.read() == b"Hello\r\n") if valid else length is None
            observation = "ignored" if length is None else f"framed {length} bytes"
            return Case(name, kind, "expected" if okay else "unexpected", observation)
    except Exception as exc:
        return Case(name, kind, "error", type(exc).__name__)


def _chunk_case(value: str, *, size: int, valid: bool) -> Case:
    kind: Literal["control", "regression"] = "control" if valid else "regression"
    name = f"chunk_size_{value}"
    body = b"x" * size
    wire = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
        + value.encode("ascii")
        + b"\r\n"
        + body
        + b"\r\n0\r\n\r\n"
    )
    try:
        with http.client.HTTPResponse(cast(Any, _HTTPInput(wire)), method="GET") as response:
            response.begin()
            actual = response.read()
        if actual != body:
            return Case(name, kind, "error", "unexpected response body")
        return Case(
            name, kind, "expected" if valid else "unexpected", f"accepted {len(actual)} bytes"
        )
    except http.client.IncompleteRead:
        return Case(name, kind, "unexpected" if valid else "expected", "rejected")
    except Exception as exc:
        return Case(name, kind, "error", type(exc).__name__)


def probe_http_client() -> list[Case]:
    cases = [_content_length_case(value, valid=True) for value in ("7", "7 ", "7\t", " 7 ")]
    cases.extend(_content_length_case(value, valid=False) for value in ("+5", "5_0", "5 0"))
    cases.extend(_chunk_case(value, size=5, valid=True) for value in ("5", "5;synthetic=1"))
    cases.extend(
        _chunk_case(value, size=size, valid=False)
        for value, size in (("+5", 5), ("0x5", 5), ("1_f", 31), (" 5", 5))
    )
    return cases


def _source(module: ModuleType) -> dict[str, str]:
    if module.__file__ is None:
        raise ValueError(f"source path unavailable for {module.__name__}")
    path = Path(module.__file__)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def build_report(*, image_ref: str | None, image_id: str | None) -> dict[str, Any]:
    checks = []
    for cve, module, cases, fixes in (
        (
            "CVE-2025-15367",
            poplib,
            probe_poplib(),
            ["b234a2b67539f787e191d2ef19a7cbdce32874e7"],
        ),
        (
            "CVE-2026-103995",
            http.client,
            probe_http_client(),
            [
                "2eb2af805c156ca52b316bb4ced5e0ab3971d0ae",
                "9f52b443c002cccfb54bda0706a9276b6b4a109d",
            ],
        ),
    ):
        checks.append(
            {
                "cve": cve,
                "status": check_status(cases),
                "source": _source(module),
                "cases": [asdict(case) for case in cases],
                "upstream_fixes": [
                    f"https://github.com/python/cpython/commit/{sha}" for sha in fixes
                ],
            }
        )
    return {
        "schema_version": 1,
        "scope": "offline behavior probes; application exploitability is not established",
        "image": {"reference": image_ref, "id": image_id},
        "runtime": {"implementation": platform.python_implementation(), "version": sys.version},
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-ref", help="Image reference supplied by the invoking CI job")
    parser.add_argument("--image-id", help="Local image ID supplied by docker image inspect")
    args = parser.parse_args(argv)
    try:
        report = build_report(image_ref=args.image_ref, image_id=args.image_id)
    except (OSError, ValueError) as exc:
        print(f"runtime probe failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if any(check["status"] == "inconclusive" for check in report["checks"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
