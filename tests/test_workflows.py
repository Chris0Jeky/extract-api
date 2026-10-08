"""Guard the immutable-image promotion workflows without calling a host or registry."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOWS = _ROOT / ".github" / "workflows"
_DIGEST_REF = "${{ env.IMAGE }}@${{ steps.build.outputs.digest }}"


def _workflow(name: str) -> dict[str, Any]:
    # BaseLoader preserves GitHub's `on` key and lets us compare literal booleans.
    # PyYAML is already in uv.lock through uvicorn; no dependency is added.
    result = yaml.load((_WORKFLOWS / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(result, dict)
    return result


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


@pytest.mark.parametrize("filename", ["image.yml", "deploy.yml"])
def test_new_workflows_pin_third_party_actions(filename: str) -> None:
    # The existing ci.yml gitleaks tag is outside this focused promotion slice.
    source = (_WORKFLOWS / filename).read_text(encoding="utf-8")
    references = re.findall(r"^\s+(?:- )?uses: (\S+)", source, flags=re.MULTILINE)
    assert references
    for reference in references:
        if not reference.startswith("actions/"):
            assert re.fullmatch(r"[\w/-]+@[0-9a-f]{40}", reference), reference
    assert "\N{EM DASH}" not in source


def test_image_pr_build_is_read_only_and_never_logs_in_or_pushes() -> None:
    image = _workflow("image.yml")
    assert set(image["on"]) == {"push", "pull_request", "workflow_dispatch"}
    assert image["on"]["push"]["branches"] == ["main"]
    assert image["permissions"] == {"contents": "read"}
    assert image["concurrency"]["group"] == "image-${{ github.ref }}"
    local = image["jobs"]["local-image"]
    assert "github.event_name == 'pull_request'" in local["if"]
    assert local.get("permissions", image["permissions"]) == {"contents": "read"}
    assert not any("docker/login-action@" in step.get("uses", "") for step in local["steps"])
    assert not any("secrets." in str(step) for step in local["steps"])
    build = _step(local, "Build once and load locally")
    assert build["with"]["load"] == "true"
    assert build["with"]["push"] == "false"
    assert "docker push" not in str(local)
    assert _step(local, "Smoke the locally built image")["env"]["IMAGE_REF"] == (
        "${{ env.IMAGE }}:sha-${{ github.sha }}"
    )
    published = image["jobs"]["published-image"]
    assert published["if"] == (
        "github.ref == 'refs/heads/main' && "
        "(github.event_name == 'push' || github.event_name == 'workflow_dispatch')"
    )


def test_build_once_per_event_with_revision_labels_and_no_latest() -> None:
    image = _workflow("image.yml")
    assert image["env"]["IMAGE"] == "ghcr.io/chris0jeky/extract-api"
    for job in image["jobs"].values():
        builds = [s for s in job["steps"] if "docker/build-push-action@" in s.get("uses", "")]
        assert len(builds) == 1
        config = builds[0]["with"]
        assert config["build-args"] == "EXTRACT_API_REVISION=${{ github.sha }}"
        assert config["platforms"] == "linux/amd64"
        assert "${{ env.IMAGE }}:sha-${{ github.sha }}" in config["tags"]
        assert "latest" not in config["tags"]
        assert "org.opencontainers.image.revision=${{ github.sha }}" in config["labels"]
        assert "org.opencontainers.image.licenses=GPL-3.0-only" in config["labels"]
        assert "org.opencontainers.image.title=extract-api" in config["labels"]
        assert (
            "org.opencontainers.image.source=https://github.com/Chris0Jeky/extract-api"
            in (config["labels"])
        )
    assert ":main" not in str(image["jobs"]["local-image"])
    # :main moves only after smoke, scan and attestation, and only to the proven digest.
    steps = image["jobs"]["published-image"]["steps"]
    names = [step.get("name", "") for step in steps]
    retag = names.index("Move the main tag to the proven digest")
    assert retag > names.index("Attest the proven image")
    assert ":main" not in str(steps[:retag])


def test_published_digest_is_smoked_scanned_and_attested_after_proof() -> None:
    job = _workflow("image.yml")["jobs"]["published-image"]
    assert job["permissions"] == {
        "contents": "read",
        "packages": "write",
        "id-token": "write",
        "attestations": "write",
        "security-events": "write",
    }
    smoke = _step(job, "Pull and smoke the pushed digest")
    assert smoke["env"]["IMAGE_REF"] == _DIGEST_REF
    assert 'docker pull "$IMAGE_REF"' in smoke["run"]
    assert 'python scripts/docker_persistence_smoke.py --image "$IMAGE_REF"' in smoke["run"]
    sbom = _step(job, "Generate SPDX JSON for the pushed digest")["with"]
    assert sbom["image"] == _DIGEST_REF
    assert sbom["format"] == "spdx-json"
    upload = _step(job, "Upload SBOM")["with"]
    assert upload["path"] == sbom["output-file"]
    assert upload["if-no-files-found"] == "error"
    summary = _step(job, "Record image identity")
    assert summary["env"]["SBOM_ARTIFACT"] == upload["name"]
    assert summary["env"]["DIGEST"] == "${{ steps.build.outputs.digest }}"
    assert '>> "$GITHUB_STEP_SUMMARY"' in summary["run"]
    scan = _step(job, "Scan the pushed digest with Grype")
    assert scan["with"]["image"] == _DIGEST_REF
    assert scan["with"]["severity-cutoff"] == "critical"
    assert scan["with"]["only-fixed"] == "true"
    assert scan["with"]["fail-build"] == "true"
    sarif = _step(job, "Upload SARIF even when the scan fails")
    assert "always()" in sarif["if"]
    assert sarif["with"]["sarif_file"] == scan["with"]["output-file"]
    attest = _step(job, "Attest the proven image")
    assert attest["with"]["subject-name"] == "${{ env.IMAGE }}"
    assert attest["with"]["subject-digest"] == "${{ steps.build.outputs.digest }}"
    assert attest["with"]["push-to-registry"] == "true"
    assert "if" not in attest  # Default success() prevents attesting failed proof.
    assert job["steps"].index(attest) > job["steps"].index(scan) > job["steps"].index(smoke)


def test_deploy_is_dispatch_only_and_serialized_in_production() -> None:
    deploy = _workflow("deploy.yml")
    assert set(deploy["on"]) == {"workflow_dispatch"}
    inputs = deploy["on"]["workflow_dispatch"]["inputs"]
    assert inputs["revision"]["required"] == "true"
    assert inputs["target"]["options"] == ["render", "railway"]
    assert inputs["target"]["default"] == "render"
    assert deploy["concurrency"] == {"group": "deploy-production", "cancel-in-progress": "false"}
    assert len(deploy["jobs"]) == 1
    job = deploy["jobs"]["deploy"]
    assert job["environment"] == "production"
    assert job["permissions"] == {"contents": "read", "packages": "read", "attestations": "read"}
    assert job["steps"][0]["name"] == "Fail loudly unless the target is provisioned"
    assert "not provisioned: $name missing" in job["steps"][0]["run"]
    assert "UNPROTECTED" in (_WORKFLOWS / "deploy.yml").read_text(encoding="utf-8")


def test_deploy_shell_uses_env_for_all_expressions() -> None:
    job = _workflow("deploy.yml")["jobs"]["deploy"]
    assert job["env"]["REVISION"] == "${{ inputs.revision }}"
    assert job["env"]["TARGET"] == "${{ inputs.target }}"
    assert job["env"]["BASE_URL"] == "${{ vars.EXTRACT_API_BASE_URL }}"
    for step in job["steps"]:
        assert "${{" not in step.get("run", ""), step.get("name")


def test_deploy_resolves_verifies_and_promotes_only_a_digest() -> None:
    job = _workflow("deploy.yml")["jobs"]["deploy"]
    validate = _step(job, "Validate revision")
    assert '[[ ! "$REVISION" =~ ^[0-9a-f]{40}$ ]]' in validate["run"]
    assert "exit 1" in validate["run"]
    resolve = _step(job, "Resolve immutable digest")
    assert 'docker buildx imagetools inspect "$IMAGE:sha-$REVISION"' in resolve["run"]
    assert "^sha256:[0-9a-f]{64}$" in resolve["run"]
    assert "image_ref=%s@%s" in resolve["run"]
    verify = _step(job, "Verify build provenance")
    assert 'gh attestation verify "oci://$IMAGE_REF" --repo Chris0Jeky/extract-api' in verify["run"]
    assert "--signer-workflow Chris0Jeky/extract-api/.github/workflows/image.yml" in verify["run"]
    assert "--source-ref refs/heads/main" in verify["run"]
    assert verify["env"]["GH_TOKEN"] == "${{ github.token }}"
    for name in ("Deploy the digest to Render", "Update Railway source and deploy the digest"):
        step = _step(job, name)
        assert step["env"]["IMAGE_REF"] == "${{ steps.resolve.outputs.image_ref }}"
        assert job["steps"].index(step) > job["steps"].index(verify)
    render = _step(job, "Deploy the digest to Render")["run"]
    assert "@uri" in render
    assert '"${RENDER_DEPLOY_HOOK_URL}&imgURL=${encoded}"' in render
    assert "--fail-with-body" in render
    assert "echo" not in render
    railway = _step(job, "Update Railway source and deploy the digest")["run"]
    assert "https://backboard.railway.com/graphql/v2" in railway
    assert "serviceInstanceUpdate" in railway and "serviceInstanceDeployV2" in railway
    assert "source: { image: $image }" in railway
    assert 'jq -n --arg service "$SERVICE_ID"' in railway
    assert railway.count("(.errors // [])") == 2
    assert railway.count("exit 1") == 2


def test_deploy_waits_for_http_200_and_revision_and_gates_fixture_smoke() -> None:
    job = _workflow("deploy.yml")["jobs"]["deploy"]
    previous = _step(job, "Record the previous revision for rollback")
    assert "::warning::" in previous["run"]
    assert "Rollback target:" in previous["run"]
    ready = _step(job, "Verify the deployed revision")["run"]
    assert "SECONDS + 600" in ready
    assert '[[ "$status" == 200 ]]' in ready
    assert "'.revision == $revision'" in ready
    assert "gh workflow run deploy.yml -f revision=%s -f target=%s" in ready
    assert "exit 1" in ready
    smoke = _step(job, "Verify one deterministic fixture extraction")
    assert smoke["if"] == "vars.EXTRACT_API_SMOKE_MODE == 'fixture'"
    assert "fixtures/invoices/invoice_0001.json" in smoke["run"]
    assert '[[ "$status" != 200 ]]' in smoke["run"]


def _bash(script: str, variables: dict[str, str]) -> subprocess.CompletedProcess[str]:
    bash = shutil.which("bash")
    if os.name == "nt":
        # WindowsApps/bash.exe is a WSL launcher, not the Git Bash used by this repo.
        git = shutil.which("git")
        candidate = Path(git).parent.parent / "bin" / "bash.exe" if git else None
        bash = str(candidate) if candidate is not None and candidate.is_file() else None
    if bash is None:
        pytest.skip("bash is required to execute workflow guard steps")
    return subprocess.run(
        [bash, "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
        env={**os.environ, **variables},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("revision", ["", "main", "a" * 39, "a" * 41, "A" * 40, "$(exit 0)"])
def test_revision_guard_rejects_invalid_inputs(revision: str) -> None:
    guard = _step(_workflow("deploy.yml")["jobs"]["deploy"], "Validate revision")["run"]
    result = _bash(guard, {"REVISION": revision})
    assert result.returncode != 0
    assert "revision must match" in result.stderr


def test_revision_guard_accepts_a_full_lowercase_sha() -> None:
    guard = _step(_workflow("deploy.yml")["jobs"]["deploy"], "Validate revision")["run"]
    assert _bash(guard, {"REVISION": "0123456789abcdef" * 2 + "01234567"}).returncode == 0


@pytest.mark.parametrize(
    ("target", "missing"),
    [
        ("render", ["EXTRACT_API_BASE_URL", "RENDER_DEPLOY_HOOK_URL"]),
        (
            "railway",
            [
                "EXTRACT_API_BASE_URL",
                "RAILWAY_PROJECT_TOKEN",
                "RAILWAY_SERVICE_ID",
                "RAILWAY_ENVIRONMENT_ID",
            ],
        ),
    ],
)
def test_unprovisioned_dispatch_fails_before_any_deploy(target: str, missing: list[str]) -> None:
    guard = _workflow("deploy.yml")["jobs"]["deploy"]["steps"][0]["run"]
    variables = dict.fromkeys(
        [
            "EXTRACT_API_BASE_URL",
            "RENDER_DEPLOY_HOOK_URL",
            "RAILWAY_PROJECT_TOKEN",
            "RAILWAY_SERVICE_ID",
            "RAILWAY_ENVIRONMENT_ID",
        ],
        "",
    )
    result = _bash(guard, {**variables, "TARGET": target})
    assert result.returncode != 0
    for name in missing:
        assert f"not provisioned: {name} missing" in result.stderr
    assert "EXTRACT_API_SMOKE_MODE must be fixture or live" in result.stderr


@pytest.mark.parametrize("target", ["render", "railway"])
def test_provisioning_guard_accepts_only_the_selected_targets_settings(target: str) -> None:
    guard = _workflow("deploy.yml")["jobs"]["deploy"]["steps"][0]["run"]
    variables = {"TARGET": target, "EXTRACT_API_BASE_URL": "present", "SMOKE_MODE": "fixture"}
    variables.update(
        {"RENDER_DEPLOY_HOOK_URL": "present"}
        if target == "render"
        else {
            "RAILWAY_PROJECT_TOKEN": "present",
            "RAILWAY_SERVICE_ID": "present",
            "RAILWAY_ENVIRONMENT_ID": "present",
        }
    )
    assert _bash(guard, variables).returncode == 0
