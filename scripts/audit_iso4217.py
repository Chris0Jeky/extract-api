"""Audit v1 currency membership against local SIX XML files without changing it.

See docs/ops/CURRENCY_AUDIT.md. Exit 0 for agreement with the explicit policy,
1 for drift needing review, and 2 for invalid input or policy configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import runpy
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, TypedDict

ROOT = Path(__file__).resolve().parent.parent
MAX_XML_BYTES = 2 * 1024 * 1024
SOURCE_URLS = {
    "current": "https://www.six-group.com/dam/download/financial-information/"
    "data-center/iso-currrency/lists/list-one.xml",
    "historical": "https://www.six-group.com/dam/download/financial-information/"
    "data-center/iso-currrency/lists/list-three.xml",
}

# Issue #10 records the v1 exclusions and retained document currencies. Never
# infer policy from IsFund or an X prefix: CHE, CHW and XDR remain accepted.
EXCLUDED_CURRENT = frozenset(
    {
        "BOV",
        "CLF",
        "COU",
        "MXV",
        "USN",
        "UYI",
        "UYW",
        "XAD",
        "XAG",
        "XAU",
        "XBA",
        "XBB",
        "XBC",
        "XBD",
        "XPD",
        "XPT",
        "XSU",
        "XTS",
        "XUA",
        "XXX",
    }
)
RETAINED_HISTORICAL = frozenset({"ANG", "BGN"})
PROVENANCE = "Local input origin and freshness are not authenticated; URLs are source references."


class AuditInputError(ValueError):
    """An input cannot support a meaningful membership audit."""


class SourceMetadata(TypedDict):
    source_url: str
    publication_date: str
    sha256: str
    record_count: int
    code_count: int
    no_currency_record_count: int


class AuditReport(TypedDict):
    report_version: int
    status: str
    provenance: str
    accepted_count: int
    accepted_current_count: int
    sources: dict[str, SourceMetadata]
    policy: dict[str, list[str]]
    findings: dict[str, list[str]]


@dataclass(frozen=True)
class CurrencyList:
    codes: frozenset[str]
    metadata: SourceMetadata


class _NoDoctypeTreeBuilder(ET.TreeBuilder):
    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        # Parser callbacks inspect decoded XML, including UTF-16 input. A byte
        # substring check alone could miss encoded DTD/entity declarations.
        raise AuditInputError("DTD and entity declarations are not allowed")


def read_source(path: Path, kind: Literal["current", "historical"]) -> CurrencyList:
    """Read a bounded XML file, validating the membership-bearing structure."""
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_XML_BYTES + 1)
    except OSError as exc:
        raise AuditInputError(f"{kind}: cannot read {path}: {exc}") from exc
    if len(raw) > MAX_XML_BYTES:
        raise AuditInputError(f"{kind}: XML exceeds {MAX_XML_BYTES} bytes")
    try:
        root = ET.fromstring(raw, parser=ET.XMLParser(target=_NoDoctypeTreeBuilder()))
    except (ET.ParseError, LookupError, ValueError) as exc:
        raise AuditInputError(f"{kind}: invalid XML: {exc}") from exc
    if root.tag != "ISO_4217":
        raise AuditInputError(f"{kind}: expected ISO_4217 root")
    publication = root.get("Pblshd", "")
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", publication):
            raise ValueError("expected YYYY-MM-DD")
        date.fromisoformat(publication)
    except ValueError as exc:
        raise AuditInputError(f"{kind}: invalid or missing Pblshd date: {publication!r}") from exc

    table_tag, record_tag = (
        ("CcyTbl", "CcyNtry") if kind == "current" else ("HstrcCcyTbl", "HstrcCcyNtry")
    )
    tables = root.findall(table_tag)
    other_table = "HstrcCcyTbl" if kind == "current" else "CcyTbl"
    if len(tables) != 1 or root.find(other_table) is not None:
        raise AuditInputError(f"{kind}: expected exactly one {table_tag} and no {other_table}")
    records = list(tables[0])
    codes: set[str] = set()
    no_currency_count = 0
    for index, record in enumerate(records, start=1):
        location = f"{kind}: record {index}"
        if record.tag != record_tag:
            raise AuditInputError(f"{location}: expected {record_tag}, got {record.tag}")
        elements = record.findall("Ccy")
        if len(elements) > 1 or (elements and len(elements[0])):
            raise AuditInputError(f"{location}: expected one plain Ccy value")
        code = record.findtext("Ccy", "")
        if not code:
            if (
                kind == "current"
                and record.findtext("CcyNm") == "No universal currency"
                and not record.findtext("CcyNbr")
            ):
                no_currency_count += 1
                continue
            raise AuditInputError(f"{location}: missing Ccy")
        if not re.fullmatch(r"[A-Z]{3}", code):
            raise AuditInputError(f"{location}: Ccy must be three uppercase ASCII letters")
        codes.add(code)
    if not codes:
        raise AuditInputError(f"{kind}: no currency codes found")
    return CurrencyList(
        codes=frozenset(codes),
        metadata={
            "source_url": SOURCE_URLS[kind],
            "publication_date": publication,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "record_count": len(records),
            "code_count": len(codes),
            "no_currency_record_count": no_currency_count,
        },
    )


def load_accepted_codes() -> frozenset[str]:
    # Load only the committed constant module, without importing schemas/__init__
    # or its runtime dependencies. This also works outside the repository cwd.
    namespace = runpy.run_path(str(ROOT / "schemas" / "iso4217.py"))
    accepted = namespace.get("ISO_4217_ALPHA")
    if not isinstance(accepted, frozenset):
        raise AuditInputError("ISO_4217_ALPHA must be a frozenset of currency codes")
    return accepted


def audit(current: CurrencyList, historical: CurrencyList, accepted: frozenset[str]) -> AuditReport:
    """Compare supplied sources with v1 policy; historical presence is not permission."""
    for name, codes in (
        ("accepted", accepted),
        ("excluded_current", EXCLUDED_CURRENT),
        ("retained_historical", RETAINED_HISTORICAL),
    ):
        if any(not isinstance(code, str) or not re.fullmatch(r"[A-Z]{3}", code) for code in codes):
            raise AuditInputError(f"{name}: codes must be three uppercase ASCII letters")
    overlap = EXCLUDED_CURRENT & RETAINED_HISTORICAL
    if overlap:
        raise AuditInputError(
            f"excluded and retained policy rules overlap: {', '.join(sorted(overlap))}"
        )
    excluded_accepted = EXCLUDED_CURRENT & accepted
    if excluded_accepted:
        raise AuditInputError(
            f"excluded codes are accepted: {', '.join(sorted(excluded_accepted))}"
        )
    findings = {
        "current_not_accepted": sorted(current.codes - EXCLUDED_CURRENT - accepted),
        "accepted_not_current": sorted(accepted - current.codes - RETAINED_HISTORICAL),
        "retained_not_accepted": sorted(RETAINED_HISTORICAL - accepted),
        "retained_missing_from_history": sorted(RETAINED_HISTORICAL - historical.codes),
        "excluded_not_current": sorted(EXCLUDED_CURRENT - current.codes),
        "retained_now_current": sorted(RETAINED_HISTORICAL & current.codes),
    }
    return {
        "report_version": 1,
        "status": "drift" if any(findings.values()) else "ok",
        "provenance": PROVENANCE,
        "accepted_count": len(accepted),
        "accepted_current_count": len(accepted & current.codes),
        "sources": {"current": current.metadata, "historical": historical.metadata},
        "policy": {
            "excluded_current": sorted(EXCLUDED_CURRENT),
            "retained_historical": sorted(RETAINED_HISTORICAL),
        },
        "findings": findings,
    }


def format_text(report: AuditReport) -> str:
    lines = [
        f"ISO-4217 audit: {'OK' if report['status'] == 'ok' else 'DRIFT (review required)'}",
        f"{report['accepted_count']} accepted; {report['accepted_current_count']} current",
        PROVENANCE,
    ]
    for kind, source in report["sources"].items():
        lines.extend(
            [
                f"{kind}: Pblshd={source['publication_date']}; "
                f"{source['record_count']} records; {source['code_count']} distinct codes; "
                f"{source['no_currency_record_count']} no-currency records",
                f"  source reference: {source['source_url']}",
                f"  SHA-256: {source['sha256']}",
            ]
        )
    for name, codes in report["policy"].items():
        lines.append(f"{name}: {', '.join(codes)}")
    for name, codes in report["findings"].items():
        lines.append(f"{name}: {', '.join(codes) if codes else 'none'}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", required=True, type=Path, help="local SIX List One XML")
    parser.add_argument("--historical", required=True, type=Path, help="local SIX List Three XML")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        report = audit(
            read_source(args.current, "current"),
            read_source(args.historical, "historical"),
            load_accepted_codes(),
        )
    except (AuditInputError, OSError) as exc:
        print(f"ISO-4217 audit: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(report, indent=2, sort_keys=True)
        if args.format == "json"
        else format_text(report)
    )
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
