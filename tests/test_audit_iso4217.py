"""The offline currency audit reports drift without changing the accepted set."""

import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "audit_iso4217.py"
FIXTURES = Path(__file__).parent / "fixtures" / "iso4217"
CURRENT = FIXTURES / "synthetic-list-one.xml"
HISTORICAL = FIXTURES / "synthetic-list-three.xml"


def _run(current=CURRENT, historical=HISTORICAL, *, output="json", cwd=None):
    return subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--current",
            str(current),
            "--historical",
            str(historical),
            "--format",
            output,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _changed_xml(tmp_path, source, *, remove=(), add=(), fund=False):
    root = ET.fromstring(source.read_bytes())
    table = root[0]
    for record in list(table):
        if record.findtext("Ccy") in remove:
            table.remove(record)
    for code in add:
        record = ET.SubElement(table, "CcyNtry" if source == CURRENT else "HstrcCcyNtry")
        ET.SubElement(record, "CtryNm").text = "SYNTHETIC TEST ENTITY"
        name = ET.SubElement(record, "CcyNm", {"IsFund": "true"} if fund else {})
        name.text = "Synthetic test currency"
        ET.SubElement(record, "Ccy").text = code
    path = tmp_path / source.name
    path.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    return path


def test_synthetic_baseline_is_clean_and_records_exact_source_bytes(tmp_path):
    # A literal, committed 178-code fixture is independent of the runtime accepted set.
    result = _run(cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["status"] == "ok"
    assert report["accepted_count"] == 160
    assert report["accepted_current_count"] == 158
    assert all(codes == [] for codes in report["findings"].values())
    assert report["policy"]["retained_historical"] == ["ANG", "BGN"]
    assert report["policy"]["excluded_current"] == [
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
    ]
    current = report["sources"]["current"]
    assert current["publication_date"] == "2026-09-17"
    assert current["record_count"] == 180
    assert current["code_count"] == 178
    assert current["no_currency_record_count"] == 1
    assert current["sha256"] == hashlib.sha256(CURRENT.read_bytes()).hexdigest()
    historical = report["sources"]["historical"]
    assert historical["publication_date"] == "2026-01-01"
    assert historical["code_count"] == 4
    assert historical["sha256"] == hashlib.sha256(HISTORICAL.read_bytes()).hexdigest()


@pytest.mark.parametrize("fund", [False, True])
def test_new_current_code_needs_review_even_when_marked_as_a_fund(tmp_path, fund):
    path = _changed_xml(tmp_path, CURRENT, add=("ZZZ", "AAA"), fund=fund)
    result = _run(current=path)
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "drift"
    assert report["findings"]["current_not_accepted"] == ["AAA", "ZZZ"]


def test_a_newly_historical_accepted_code_still_needs_a_retention_decision(tmp_path):
    current = _changed_xml(tmp_path, CURRENT, remove=("GBP",))
    historical = _changed_xml(tmp_path, HISTORICAL, add=("GBP",))
    result = _run(current=current, historical=historical)
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["findings"]["accepted_not_current"] == ["GBP"]


def test_retained_code_missing_from_history_is_reported(tmp_path):
    path = _changed_xml(tmp_path, HISTORICAL, remove=("ANG",))
    result = _run(historical=path)
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["findings"]["retained_missing_from_history"] == ["ANG"]


def test_exclusion_removal_and_retained_code_return_are_reported(tmp_path):
    path = _changed_xml(tmp_path, CURRENT, remove=("XAD",), add=("ANG",))
    result = _run(current=path)
    assert result.returncode == 1, result.stderr
    findings = json.loads(result.stdout)["findings"]
    assert findings["excluded_not_current"] == ["XAD"]
    assert findings["retained_now_current"] == ["ANG"]


def test_json_output_is_repeatable_and_inputs_are_unchanged(tmp_path):
    paths = (CURRENT, HISTORICAL, ROOT / "schemas" / "iso4217.py")
    before = [path.read_bytes() for path in paths]
    first = _run(cwd=tmp_path)
    second = _run(cwd=tmp_path)
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert [path.read_bytes() for path in paths] == before


def test_human_report_explains_status_and_provenance_limits():
    result = _run(output="text")
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
    assert "160 accepted" in result.stdout
    assert "158 current" in result.stdout
    assert "ANG, BGN" in result.stdout
    assert "178 distinct codes" in result.stdout
    assert hashlib.sha256(CURRENT.read_bytes()).hexdigest() in result.stdout
    assert "not authenticated" in result.stdout


@pytest.mark.parametrize(
    ("xml", "diagnostic"),
    [
        ("<ISO_4217", "invalid XML"),
        ("<html><body>Unavailable</body></html>", "ISO_4217"),
        ('<ISO_4217 Pblshd="2026-09-17"><CcyTbl/></ISO_4217>', "no currency codes"),
        ('<ISO_4217 Pblshd="2026-09-17"><HstrcCcyTbl/></ISO_4217>', "CcyTbl"),
        ("<ISO_4217><CcyTbl/></ISO_4217>", "Pblshd"),
        ('<ISO_4217 Pblshd="2026-02-30"><CcyTbl/></ISO_4217>', "Pblshd"),
        ('<ISO_4217 Pblshd="20260917"><CcyTbl/></ISO_4217>', "Pblshd"),
        (
            '<ISO_4217 Pblshd="2026-09-17"><CcyTbl><CcyNtry><Ccy>usd</Ccy>'
            "</CcyNtry></CcyTbl></ISO_4217>",
            "three uppercase ASCII letters",
        ),
        (
            '<ISO_4217 Pblshd="2026-09-17"><CcyTbl><CcyNtry><Ccy> US</Ccy>'
            "</CcyNtry></CcyTbl></ISO_4217>",
            "three uppercase ASCII letters",
        ),
        (
            '<ISO_4217 Pblshd="2026-09-17"><CcyTbl><CcyNtry><CcyNm>Dollar</CcyNm>'
            "</CcyNtry></CcyTbl></ISO_4217>",
            "missing Ccy",
        ),
        (
            '<!DOCTYPE ISO_4217 [<!ENTITY currency "USD">]>'
            '<ISO_4217 Pblshd="2026-09-17"><CcyTbl><CcyNtry><Ccy>&currency;</Ccy>'
            "</CcyNtry></CcyTbl></ISO_4217>",
            "DTD",
        ),
    ],
)
def test_invalid_current_input_fails_without_a_misleading_report(tmp_path, xml, diagnostic):
    path = tmp_path / "invalid.xml"
    path.write_text(xml, encoding="utf-8")
    result = _run(current=path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert diagnostic in result.stderr
    assert "Traceback" not in result.stderr


def test_missing_input_and_swapped_sources_are_input_errors(tmp_path):
    missing = _run(current=tmp_path / "missing.xml")
    assert missing.returncode == 2
    assert missing.stdout == ""
    assert "cannot read" in missing.stderr
    swapped = _run(current=HISTORICAL, historical=CURRENT)
    assert swapped.returncode == 2
    assert swapped.stdout == ""
    assert "CcyTbl" in swapped.stderr


def test_removing_a_retained_code_from_the_accepted_set_is_drift():
    from scripts import audit_iso4217 as module

    report = module.audit(
        module.read_source(CURRENT, "current"),
        module.read_source(HISTORICAL, "historical"),
        module.load_accepted_codes() - {"ANG"},
    )
    assert report["status"] == "drift"
    assert report["findings"]["retained_not_accepted"] == ["ANG"]


def test_accepting_an_excluded_code_is_a_policy_error():
    from scripts import audit_iso4217 as module

    with pytest.raises(module.AuditInputError, match=r"excluded.*accepted"):
        module.audit(
            module.read_source(CURRENT, "current"),
            module.read_source(HISTORICAL, "historical"),
            module.load_accepted_codes() | {"XAU"},
        )


def test_overlapping_exclusion_and_retention_is_a_policy_error(monkeypatch):
    from scripts import audit_iso4217 as module

    monkeypatch.setattr(module, "RETAINED_HISTORICAL", frozenset({"ANG", "BGN", "XAU"}))
    with pytest.raises(module.AuditInputError, match="overlap"):
        module.audit(
            module.read_source(CURRENT, "current"),
            module.read_source(HISTORICAL, "historical"),
            module.load_accepted_codes(),
        )


@pytest.mark.parametrize("code", ["usd", "USD ", "ÜSD", 123])
def test_malformed_accepted_codes_are_an_input_error(code):
    from scripts import audit_iso4217 as module

    with pytest.raises(module.AuditInputError, match=r"accepted.*uppercase ASCII"):
        module.audit(
            module.read_source(CURRENT, "current"),
            module.read_source(HISTORICAL, "historical"),
            module.load_accepted_codes() | {code},
        )


def test_policy_error_uses_exit_two_without_printing_a_report(monkeypatch, capsys):
    from scripts import audit_iso4217 as module

    accepted = module.load_accepted_codes() | {"XAU"}
    monkeypatch.setattr(module, "load_accepted_codes", lambda: accepted)
    result = module.main(["--current", str(CURRENT), "--historical", str(HISTORICAL)])
    captured = capsys.readouterr()
    assert result == 2
    assert captured.out == ""
    assert "excluded" in captured.err


def test_encoded_dtd_is_rejected_before_entities_are_processed(tmp_path):
    path = tmp_path / "encoded.xml"
    path.write_bytes(
        (
            '<?xml version="1.0" encoding="UTF-16"?>'
            '<!DOCTYPE ISO_4217 SYSTEM "file:///not-read.dtd">'
            '<ISO_4217 Pblshd="2026-09-17"><CcyTbl/></ISO_4217>'
        ).encode("utf-16")
    )
    result = _run(current=path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "DTD" in result.stderr
    assert "Traceback" not in result.stderr


def test_oversized_input_fails_before_parsing(tmp_path):
    path = tmp_path / "large.xml"
    path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    result = _run(current=path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "exceeds" in result.stderr


def test_record_order_and_unknown_metadata_do_not_change_membership(tmp_path):
    root = ET.fromstring(CURRENT.read_bytes())
    table = root[0]
    table[:] = list(reversed(table))
    ET.SubElement(table[-1], "FutureMetadata").text = "harmless extra detail"
    path = tmp_path / "reordered.xml"
    path.write_bytes(ET.tostring(root))
    result = _run(current=path)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert all(codes == [] for codes in report["findings"].values())
    assert report["sources"]["current"]["code_count"] == 178
    assert report["sources"]["current"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "replacement",
    [
        "<Ccy>USD</Ccy><Ccy>EUR</Ccy>",
        "<Ccy><Unexpected>USD</Unexpected></Ccy>",
    ],
)
def test_ambiguous_code_elements_are_not_silently_ignored(tmp_path, replacement):
    text = CURRENT.read_text(encoding="utf-8").replace("<Ccy>AED</Ccy>", replacement, 1)
    path = tmp_path / "ambiguous.xml"
    path.write_text(text, encoding="utf-8")
    result = _run(current=path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "one plain Ccy" in result.stderr


def test_missing_historical_code_is_invalid_input(tmp_path):
    text = HISTORICAL.read_text(encoding="utf-8").replace("<Ccy>ANG</Ccy>", "", 1)
    path = tmp_path / "bad-history.xml"
    path.write_text(text, encoding="utf-8")
    result = _run(historical=path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "historical" in result.stderr
    assert "missing Ccy" in result.stderr


def test_human_drift_report_names_the_code_requiring_review(tmp_path):
    path = _changed_xml(tmp_path, CURRENT, add=("AAA",))
    result = _run(current=path, output="text")
    assert result.returncode == 1, result.stderr
    assert "DRIFT (review required)" in result.stdout
    assert "current_not_accepted: AAA" in result.stdout
