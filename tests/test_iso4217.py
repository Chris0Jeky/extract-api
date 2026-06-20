"""The committed ISO-4217 active code set is well-formed and current."""

from schemas.iso4217 import ISO_4217_ALPHA


def test_count_snapshot():
    # Snapshot size guards against accidental edits; bump deliberately when the
    # active code set changes (e.g. the ANG -> XCG transition noted in the module).
    assert len(ISO_4217_ALPHA) == 156


def test_includes_common_and_supranational_currencies():
    for code in ("GBP", "USD", "EUR", "JPY", "INR", "CNY", "BRL", "XOF", "XAF", "XCD", "XDR"):
        assert code in ISO_4217_ALPHA


def test_excludes_metals_test_and_fund_codes():
    for code in ("XAU", "XAG", "XPT", "XPD", "XTS", "XXX", "XUA", "XSU"):
        assert code not in ISO_4217_ALPHA


def test_excludes_superseded_codes():
    for code in ("VEF", "MRO", "STD", "BYR", "RUR", "ZWL", "SLL", "DEM", "FRF", "ITL"):
        assert code not in ISO_4217_ALPHA


def test_every_code_is_three_upper_ascii_letters():
    for code in ISO_4217_ALPHA:
        assert len(code) == 3
        assert code.isascii() and code.isalpha() and code.isupper()
