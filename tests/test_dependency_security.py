"""Keep the CA bundle above the reviewed security floor without calling the network."""

import hashlib
import ssl
import tomllib
from importlib.metadata import version
from pathlib import Path

import certifi

_ROOT = Path(__file__).resolve().parent.parent
_CERTIFI_FLOOR = (2026, 10, 19)


def test_certifi_security_floor_is_declared_and_locked() -> None:
    # GHSA-6q48-6c7w-9gw2: emSign intermediates were revoked after key compromise.
    # https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "certifi>=2026.10.19" in project["project"]["dependencies"]
    lock = tomllib.loads((_ROOT / "uv.lock").read_text(encoding="utf-8"))
    (locked,) = [package for package in lock["package"] if package["name"] == "certifi"]
    assert tuple(map(int, locked["version"].split("."))) >= _CERTIFI_FLOOR
    assert locked["source"] == {"registry": "https://pypi.org/simple"}
    assert all(wheel["hash"].startswith("sha256:") for wheel in locked["wheels"])


def test_installed_certifi_excludes_revoked_emsign_g3_root() -> None:
    assert tuple(map(int, version("certifi").split("."))) >= _CERTIFI_FLOOR
    # Upstream 662df63 restores the three unaffected emSign roots in 2026.10.19.
    # Check the affected G3 certificate's DER fingerprint, not every emSign name.
    revoked = "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
    context = ssl.create_default_context(cafile=certifi.where())
    trusted = context.get_ca_certs(binary_form=True)
    assert trusted
    assert revoked not in {hashlib.sha256(certificate).hexdigest() for certificate in trusted}
