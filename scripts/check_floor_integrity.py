"""Check the vendored floor's provenance pin and raw bytes without executing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ".agent-harness/floor-integrity.json"
SOURCES = {
    ".claude/hooks/dispatch.py": "templates/hooks/dispatch.py",
    ".claude/hooks/smoke_test.py": "templates/hooks/smoke_test.py",
}


def check_floor(root: Path) -> list[str]:
    try:
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"{MANIFEST}: cannot read manifest: {exc}"]
    if not isinstance(manifest, dict):
        return [f"{MANIFEST}: must be a JSON object"]

    errors = []
    if manifest.get("upstream_repository") != "Chris0Jeky/agent-harness":
        errors.append(f"{MANIFEST}: upstream_repository must be Chris0Jeky/agent-harness")
    commit = manifest.get("upstream_commit")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        errors.append(f"{MANIFEST}: upstream_commit must be a full lowercase commit SHA")
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != set(SOURCES):
        return [*errors, f"{MANIFEST}: must pin exactly {', '.join(SOURCES)}"]

    for name, upstream_path in SOURCES.items():
        entry = files[name]
        if not isinstance(entry, dict) or entry.get("upstream_path") != upstream_path:
            errors.append(f"{MANIFEST}: {name}: upstream_path must be {upstream_path}")
            continue
        expected = entry.get("sha256")
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            errors.append(f"{MANIFEST}: {name}: sha256 must be 64 lowercase hex characters")
            continue
        try:
            actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        except OSError as exc:
            errors.append(f"{name}: cannot read file: {exc}")
            continue
        if actual != expected:
            errors.append(f"{name}: SHA-256 mismatch: expected {expected}, got {actual}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root to verify")
    args = parser.parse_args()
    errors = check_floor(args.root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Vendored floor matches its integrity pin (2 files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
