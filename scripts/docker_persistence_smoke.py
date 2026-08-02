"""Exercise the Docker image's non-root and durable idempotency contract offline."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FIXTURE = _REPO_ROOT / "fixtures" / "invoices" / "invoice_0001.json"
_READY_TIMEOUT_S = 30.0


def _run(
    *args: str,
    capture_output: bool = False,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=_REPO_ROOT,
        text=True,
        check=check,
        capture_output=capture_output,
        env=env,
    )


def _fixture_request() -> tuple[dict[str, str], str]:
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    expected = fixture["expected"]
    if not isinstance(expected, dict):
        raise RuntimeError("invoice_0001 expected data must be an object")
    return (
        {
            "doc_type": str(fixture["doc_type"]),
            "schema_version": str(fixture["schema_version"]),
            "content": str(fixture["content"]),
            "provider": "openai",
        },
        json.dumps(expected, separators=(",", ":")),
    )


def _assert_compose_contract() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        env_file = Path(temp_dir) / "fixture.env"
        env_file.write_text(
            "LLM_PROVIDER_MODE=fixture\n"
            "FIXTURE_CANNED_TEXT={}\n"
            "IDEMPOTENCY_DB_PATH=idempotency.sqlite\n",
            encoding="utf-8",
        )
        env = dict(os.environ)
        env["EXTRACT_API_ENV_FILE"] = str(env_file)
        rendered = _run(
            "docker",
            "compose",
            "config",
            "--format",
            "json",
            capture_output=True,
            env=env,
        )

    config = json.loads(rendered.stdout)
    services = config.get("services")
    if not isinstance(services, dict):
        raise RuntimeError("docker compose config has no services object")
    service = services.get("extract-api")
    if not isinstance(service, dict):
        raise RuntimeError("docker compose config has no extract-api service")

    environment = service.get("environment")
    if not isinstance(environment, dict) or environment.get("IDEMPOTENCY_DB_PATH") != (
        "/data/idempotency.sqlite"
    ):
        raise RuntimeError("compose must set IDEMPOTENCY_DB_PATH to /data/idempotency.sqlite")

    mounts = service.get("volumes")
    if not isinstance(mounts, list) or not any(
        isinstance(mount, dict)
        and mount.get("type") == "volume"
        and mount.get("source") == "idempotency-data"
        and mount.get("target") == "/data"
        for mount in mounts
    ):
        raise RuntimeError("compose must mount idempotency-data at /data")

    volumes = config.get("volumes")
    if not isinstance(volumes, dict) or "idempotency-data" not in volumes:
        raise RuntimeError("compose must declare the idempotency-data named volume")


def _assert_image_user(image: str) -> None:
    user = _run(
        "docker",
        "image",
        "inspect",
        image,
        "--format",
        "{{.Config.User}}",
        capture_output=True,
    ).stdout.strip()
    if not user or user in {"0", "0:0", "root", "root:root"}:
        raise RuntimeError(f"Docker image must configure a non-root user, got {user!r}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _start_container(
    *,
    image: str,
    container: str,
    volume: str,
    port: int,
    canned_text: str,
) -> None:
    _run(
        "docker",
        "run",
        "-d",
        "--name",
        container,
        "-v",
        f"{volume}:/data",
        "-p",
        f"127.0.0.1:{port}:8200",
        "-e",
        "LLM_PROVIDER_MODE=fixture",
        "-e",
        f"FIXTURE_CANNED_TEXT={canned_text}",
        image,
    )


def _wait_for_health(port: int) -> None:
    deadline = time.monotonic() + _READY_TIMEOUT_S
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as response:
                if response.status == 200:
                    return
        except (HTTPError, URLError, OSError) as exc:
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"Docker service did not become healthy: {last_error}")


def _post(port: int, payload: dict[str, str], key: str) -> tuple[int, dict[str, object]]:
    request = Request(
        f"http://127.0.0.1:{port}/v1/extract",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Idempotency-Key": key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            body = response.read()
            return response.status, json.loads(body)
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _is_replayed(body: dict[str, object]) -> bool:
    meta = body.get("meta")
    if not isinstance(meta, dict) or not isinstance(meta.get("replayed"), bool):
        raise RuntimeError(f"response has no boolean meta.replayed: {body}")
    return meta["replayed"]


def _remove_container(container: str) -> None:
    _run("docker", "stop", container, check=False, capture_output=True)
    _run("docker", "rm", container, check=False, capture_output=True)


def _cleanup(container: str | None, volume: str | None) -> None:
    if container is not None:
        _remove_container(container)
    if volume is not None:
        _run("docker", "volume", "rm", volume, check=False, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="already-built image to exercise")
    args = parser.parse_args()

    container: str | None = None
    volume: str | None = None
    try:
        _assert_compose_contract()
        _assert_image_user(args.image)
        payload, valid_canned_text = _fixture_request()
        resource_suffix = uuid.uuid4().hex[:12]
        container = f"extract-api-persistence-smoke-{resource_suffix}"
        volume = f"extract-api-persistence-smoke-{resource_suffix}"
        port = _free_port()
        _run("docker", "volume", "create", volume)

        _start_container(
            image=args.image,
            container=container,
            volume=volume,
            port=port,
            canned_text=valid_canned_text,
        )
        _wait_for_health(port)
        uid = _run("docker", "exec", container, "id", "-u", capture_output=True).stdout.strip()
        if uid == "0":
            raise RuntimeError("Docker service is running as root")

        first_status, first_body = _post(port, payload, "docker-persistence-key")
        if first_status != 200 or _is_replayed(first_body):
            raise RuntimeError(
                f"first keyed request did not succeed normally: {first_status} {first_body}"
            )
        _run("docker", "exec", container, "test", "-f", "/data/idempotency.sqlite")

        _remove_container(container)
        _start_container(
            image=args.image,
            container=container,
            volume=volume,
            port=port,
            canned_text="{}",
        )
        _wait_for_health(port)

        replay_status, replay_body = _post(port, payload, "docker-persistence-key")
        if replay_status != 200 or not _is_replayed(replay_body):
            raise RuntimeError(
                f"recreated container lost replay state: {replay_status} {replay_body}"
            )
        fresh_status, fresh_body = _post(port, payload, "docker-persistence-fresh-key")
        if fresh_status != 422 or fresh_body.get("error") != "validation_failed":
            raise RuntimeError(
                f"fresh key did not use the invalid fixture response: {fresh_status} {fresh_body}"
            )
    finally:
        _cleanup(container, volume)

    print("DOCKER PERSISTENCE SMOKE OK: non-root image, writable /data, replay survives recreate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
