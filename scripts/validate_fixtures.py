"""Validate fixtures against their registered schema and the labeling rules.

Real and deterministic. Exit 0 if every fixture is well-formed and its expected
label validates against the strict schema; exit 1 (fail loud) on any problem.
DRAFT labels are validated for structure but are never counted as ground truth by
the accuracy harness.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import ValidationError

from schemas.registry import UnknownSchema, resolve

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"

REQUIRED_KEYS = {
    "fixture_id",
    "doc_type",
    "schema_version",
    "source",
    "label_status",
    "content",
    "expected",
}
VALID_SOURCES = {"real_anonymized", "synthetic"}
VALID_STATUS = {"DRAFT", "REVIEWED"}


def validate_file(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON: {exc}"]

    if not isinstance(data, dict):
        return [f"{path.name}: fixture must be a JSON object, got {type(data).__name__}"]

    missing = REQUIRED_KEYS - data.keys()
    if missing:
        return [f"{path.name}: missing keys {sorted(missing)}"]

    errs: list[str] = []
    if data["source"] not in VALID_SOURCES:
        errs.append(f"{path.name}: source must be one of {sorted(VALID_SOURCES)}")
    if data["label_status"] not in VALID_STATUS:
        errs.append(f"{path.name}: label_status must be one of {sorted(VALID_STATUS)}")

    try:
        model = resolve(data["doc_type"], data["schema_version"])
    except UnknownSchema as exc:
        return [*errs, f"{path.name}: {exc}"]

    try:
        model.model_validate_json(json.dumps(data["expected"]))
    except ValidationError as exc:
        errs.append(
            f"{path.name}: expected label fails {data['doc_type']}.{data['schema_version']}: "
            f"{exc.error_count()} error(s)"
        )
    return errs


def main() -> int:
    files = sorted(FIXTURES.rglob("*.json"))
    if not files:
        print("fixtures-validate: no fixtures found yet (OK at M0).")
        return 0

    all_errs: list[str] = []
    counts: dict[str, dict[str, int]] = {}
    for path in files:
        errs = validate_file(path)
        all_errs.extend(errs)
        if not errs:
            data = json.loads(path.read_text(encoding="utf-8"))
            bucket = counts.setdefault(data["doc_type"], {"DRAFT": 0, "REVIEWED": 0})
            bucket[data["label_status"]] += 1

    for doc_type, c in sorted(counts.items()):
        print(f"  {doc_type}: {c['REVIEWED']} REVIEWED, {c['DRAFT']} DRAFT")

    if all_errs:
        print(f"fixtures-validate FAILED ({len(all_errs)} problem(s)):", file=sys.stderr)
        for err in all_errs:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"fixtures-validate OK: {len(files)} fixtures valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
