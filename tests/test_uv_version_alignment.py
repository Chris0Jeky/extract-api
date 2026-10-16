"""Dependabot bumps the Docker uv image and the setup-uv workflows separately, so CI and the
image can drift to different lock readers; this keeps every uv pin and its docs in step (#160)."""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SITES = {
    "Dockerfile": r"ghcr\.io/astral-sh/uv:(\d+\.\d+\.\d+)",
    ".github/workflows/ci.yml": r'version: "(\d+\.\d+\.\d+)"',
    ".github/workflows/loadtest.yml": r'version: "(\d+\.\d+\.\d+)"',
    "README.md": r"installed by uv (\d+\.\d+\.\d+)",
    "docs/adr/0001-dependency-versions.md": r"Docker runtime uses uv (\d+\.\d+\.\d+)",
}


def test_every_uv_pin_names_the_same_version():
    found = {}
    for path, pattern in _SITES.items():
        versions = set(re.findall(pattern, (_ROOT / path).read_text(encoding="utf-8")))
        assert len(versions) == 1, f"{path}: want one uv version for {pattern!r}, got {versions}"
        found[path] = versions.pop()
    assert len(set(found.values())) == 1, f"uv versions differ: {found}"
