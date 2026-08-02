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

from harness.run_accuracy import FIXTURE_DIRS
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
    # isinstance guards first: a non-str (e.g. list) would raise TypeError on `in`.
    if not isinstance(data["source"], str) or data["source"] not in VALID_SOURCES:
        errs.append(f"{path.name}: source must be one of {sorted(VALID_SOURCES)}")
    if not isinstance(data["label_status"], str) or data["label_status"] not in VALID_STATUS:
        errs.append(f"{path.name}: label_status must be one of {sorted(VALID_STATUS)}")
    # content is the raw document text the accuracy harness scores against; a present
    # but null/numeric/blank value must fail loudly rather than count as a valid fixture.
    if not isinstance(data["content"], str) or not data["content"].strip():
        errs.append(f"{path.name}: content must be a non-empty string")
    if not isinstance(data["expected"], dict):
        errs.append(f"{path.name}: expected must be a JSON object")
        return errs

    # resolve() indexes a dict keyed by strings; an unhashable metadata value (for example a
    # list) would otherwise raise TypeError and abort the corpus scan instead of reporting this
    # fixture. Keep the validator strict: malformed values are errors, never coerced.
    doc_type = data["doc_type"]
    schema_version = data["schema_version"]
    valid_doc_type = isinstance(doc_type, str) and bool(doc_type.strip())
    valid_schema_version = isinstance(schema_version, str) and bool(schema_version.strip())
    if not valid_doc_type:
        errs.append(f"{path.name}: doc_type must be a non-empty string")
    if not valid_schema_version:
        errs.append(f"{path.name}: schema_version must be a non-empty string")
    if not valid_doc_type or not valid_schema_version:
        return errs

    try:
        model = resolve(doc_type, schema_version)
    except UnknownSchema as exc:
        return [*errs, f"{path.name}: {exc}"]

    try:
        model.model_validate_json(json.dumps(data["expected"]))
    except ValidationError as exc:
        errs.append(
            f"{path.name}: expected label fails {doc_type}.{schema_version}: "
            f"{exc.error_count()} error(s)"
        )

    # Placement invariant (issue #63): a REVIEWED fixture must sit in the directory its doc_type
    # maps to. The accuracy harness only checks placement for the doc_type it is run for, so a
    # single-doc-type run silently under-counts a misfiled fixture (an invoice saved under
    # job_postings/ is invisible to --doc-type invoice). Enforcing it here, corpus-wide on every
    # CI run, catches misplacement from both directions independent of any harness run. DRAFT and
    # unlabelled fixtures are exempt: they are never scored, wherever they sit (as in the harness).
    if data["label_status"] == "REVIEWED":
        # doc_type resolved above (an unknown doc_type returned early), so it is a registered type
        # and normally mapped; a missing mapping means the registry and FIXTURE_DIRS have drifted,
        # which is itself a loud setup error rather than something to skip silently.
        expected_dir = FIXTURE_DIRS.get(data["doc_type"])
        # resolve() first so a relative path or bare filename (e.g. invoked from inside the
        # fixtures directory) still yields the real parent directory, not an empty/relative name
        # that would read as a spurious placement error.
        actual_dir = path.resolve().parent.name
        if expected_dir is None:
            errs.append(
                f"{path.name}: REVIEWED fixture doc_type {data['doc_type']!r} has no fixtures "
                "directory mapping (registry and FIXTURE_DIRS have drifted)"
            )
        elif actual_dir != expected_dir:
            errs.append(
                f"{path.name}: REVIEWED fixture doc_type {data['doc_type']!r} belongs in "
                f"{expected_dir}/ but sits in {actual_dir}/"
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
