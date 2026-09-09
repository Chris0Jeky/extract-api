#!/usr/bin/env python3
"""Safely copy this bundle into a repository-local .acceleration directory.

Dry-run is the default. The script never edits application source, issues or git settings.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True, help="Path to the extract-api checkout")
    parser.add_argument("--apply", action="store_true", help="Perform the copy; otherwise print a plan")
    parser.add_argument("--force", action="store_true", help="Allow overwriting existing bundle-copy files")
    parser.add_argument("--without-candidates", action="store_true", help="Skip candidate-fixtures")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo.expanduser().resolve()
    if not repo.is_dir():
        raise SystemExit(f"repository path does not exist: {repo}")
    if not (repo / ".git").exists():
        raise SystemExit(f"not a git checkout (missing .git): {repo}")
    if repo == BUNDLE or BUNDLE in repo.parents:
        raise SystemExit("refusing to copy the bundle into itself")

    dest = repo / ".acceleration" / "extract-api"
    sources = [p for p in sorted(BUNDLE.rglob("*")) if p.is_file()]
    if args.without_candidates:
        sources = [p for p in sources if "candidate-fixtures" not in p.relative_to(BUNDLE).parts]

    conflicts = []
    for src in sources:
        target = dest / src.relative_to(BUNDLE)
        if target.exists() and not args.force:
            conflicts.append(target)
    if conflicts:
        print("Refusing to overwrite existing files. Re-run with --force only after review:", file=sys.stderr)
        for p in conflicts[:30]:
            print(f"  {p}", file=sys.stderr)
        if len(conflicts) > 30:
            print(f"  ... and {len(conflicts)-30} more", file=sys.stderr)
        return 2

    print(f"Bundle: {BUNDLE}")
    print(f"Destination: {dest}")
    print(f"Files: {len(sources)}")
    if not args.apply:
        print("DRY RUN: no files copied. Add --apply to copy safely.")
        return 0

    for src in sources:
        target = dest / src.relative_to(BUNDLE)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    print("Copy complete. No application source or git metadata was modified.")
    print(f"Next: python {dest / 'scripts' / 'validate_bundle.py'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
