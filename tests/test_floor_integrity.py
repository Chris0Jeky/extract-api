"""Pin canonical bytes without importing the floor or running its large matrix."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ".agent-harness/floor-integrity.json"
CHECKER = ROOT / "scripts/check_floor_integrity.py"
FILES = (".claude/hooks/dispatch.py", ".claude/hooks/smoke_test.py")


@pytest.fixture
def floor_tree(tmp_path):
    for name in (*FILES, MANIFEST):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


def _check(root):
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def _change_manifest(root, change):
    path = root / MANIFEST
    document = json.loads(path.read_text(encoding="utf-8"))
    change(document)
    path.write_text(json.dumps(document), encoding="utf-8")


def test_committed_bytes_match_the_canonical_pin():
    result = _check(ROOT)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", FILES)
def test_changed_bytes_fail_with_the_affected_path(floor_tree, name):
    path = floor_tree / name
    path.write_bytes(path.read_bytes() + b"\n# unexpected local edit\n")
    result = _check(floor_tree)
    assert result.returncode == 1
    assert f"{name}: SHA-256 mismatch" in result.stderr


@pytest.mark.parametrize("name", FILES)
def test_crlf_drift_is_not_normalized_away(floor_tree, name):
    path = floor_tree / name
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    result = _check(floor_tree)
    assert result.returncode == 1
    assert f"{name}: SHA-256 mismatch" in result.stderr


@pytest.mark.parametrize("name", FILES)
def test_missing_file_fails(floor_tree, name):
    (floor_tree / name).unlink()
    result = _check(floor_tree)
    assert result.returncode == 1
    assert name in result.stderr


@pytest.mark.parametrize("name", FILES)
def test_a_pin_cannot_be_silently_dropped(floor_tree, name):
    _change_manifest(floor_tree, lambda document: document["files"].pop(name))
    result = _check(floor_tree)
    assert result.returncode == 1
    assert "must pin exactly" in result.stderr


@pytest.mark.parametrize("content", ["{broken", "[]", '{"files": {}}'])
def test_invalid_or_empty_manifest_fails(floor_tree, content):
    (floor_tree / MANIFEST).write_text(content, encoding="utf-8")
    result = _check(floor_tree)
    assert result.returncode == 1
    assert MANIFEST in result.stderr


@pytest.mark.parametrize("commit", ["main", "4c85b62", None])
def test_upstream_requires_a_full_immutable_commit(floor_tree, commit):
    _change_manifest(floor_tree, lambda document: document.update(upstream_commit=commit))
    result = _check(floor_tree)
    assert result.returncode == 1
    assert "upstream_commit" in result.stderr


@pytest.mark.parametrize("digest", ["", "not-a-digest", None])
def test_invalid_digest_fails(floor_tree, digest):
    _change_manifest(floor_tree, lambda document: document["files"][FILES[0]].update(sha256=digest))
    result = _check(floor_tree)
    assert result.returncode == 1
    assert "sha256" in result.stderr


def test_ordinary_gates_check_integrity_without_running_the_matrix():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    quick = next(line for line in makefile.splitlines() if line.startswith("ci-quick:"))
    assert "check-floor" in quick
    assert "test-floor" not in quick
    workflow = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    commands = "\n".join(step.get("run", "") for step in workflow["jobs"]["quality"]["steps"])
    assert "python scripts/check_floor_integrity.py" in commands
    assert ".claude/hooks/smoke_test.py" not in commands


def test_matrix_workflow_is_conditional_and_uses_pinned_tools():
    workflow = yaml.load((ROOT / ".github/workflows/floor.yml").read_text(), Loader=yaml.BaseLoader)
    paths = {
        *FILES,
        MANIFEST,
        "scripts/check_floor_integrity.py",
        "tests/test_floor_integrity.py",
        "tests/test_uv_version_alignment.py",
        ".github/workflows/floor.yml",
        ".github/workflows/ci.yml",
        ".gitattributes",
        "Makefile",
    }
    assert set(workflow["on"]) == {"pull_request", "push"}
    assert set(workflow["on"]["pull_request"]["paths"]) == paths
    assert set(workflow["on"]["push"]["paths"]) == paths
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["floor"]
    assert set(job["strategy"]["matrix"]["os"]) == {"ubuntu-latest", "windows-latest"}
    assert int(job["timeout-minutes"]) >= 15
    for step in job["steps"]:
        if "uses" in step:
            assert re.fullmatch(r"[\w-]+/[\w-]+@[0-9a-f]{40}", step["uses"])
    commands = [step["run"] for step in job["steps"] if "run" in step]
    assert commands == [
        "uv run --no-project --python 3.13 python scripts/check_floor_integrity.py",
        "uv run --no-project --python 3.13 python .claude/hooks/smoke_test.py",
    ]


def test_python_checkout_keeps_the_pinned_lf_bytes_on_windows():
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.py text eol=lf" in attributes.splitlines()
