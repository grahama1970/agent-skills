"""Minimal Battle Docker launch-spec validation.

The host process is the control plane. Anything that runs target, generated, or
judge-adjacent executable code must cross a Docker-shaped boundary before the
production adapter will launch it.
"""
from __future__ import annotations

import shlex
from typing import Any

_OPTIONS_WITH_VALUES = {
    "--add-host",
    "--cpus",
    "--entrypoint",
    "--env",
    "--hostname",
    "--memory",
    "--mount",
    "--name",
    "--network",
    "--platform",
    "--user",
    "--volume",
    "--workdir",
    "-e",
    "-h",
    "-m",
    "-u",
    "-v",
    "-w",
}


def extract_docker_run_image(command: str) -> str | None:
    """Return the image from a plain `docker run` command, or None."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    if len(parts) < 3 or parts[0] != "docker" or parts[1] != "run":
        return None
    index = 2
    while index < len(parts):
        token = parts[index]
        if token == "--":
            return parts[index + 1] if index + 1 < len(parts) else None
        if not token.startswith("-"):
            return token
        name = token.split("=", 1)[0]
        index += 2 if name in _OPTIONS_WITH_VALUES and "=" not in token else 1
    return None

DISALLOWED_MOUNTS = {
    "/var/run/docker.sock",
    "/run/docker.sock",
}
DISALLOWED_MOUNT_FRAGMENTS = (
    ":/root/.ssh",
    ":/home/graham/.ssh",
    ":/root/.config",
    ":/home/graham/.config",
)


def validate_docker_run_command(command: str) -> dict[str, Any]:
    """Return a fail-closed validation receipt for a target launch command.

    This is intentionally narrow: Battle's current production adapter accepts a
    shell command template, so the safe minimum is to reject anything that is not
    plainly `docker run` and reject obvious host-escape mounts. A later typed
    launch-spec service can replace this without weakening the boundary.
    """
    receipt: dict[str, Any] = {
        "schema": "battle.docker_launch_validation.v1",
        "status": "PASS",
        "problems": [],
    }
    if not isinstance(command, str) or not command.strip():
        receipt["status"] = "FAIL"
        receipt["problems"].append("docker-command-empty")
        return receipt
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        receipt["status"] = "FAIL"
        receipt["problems"].append(f"docker-command-unparseable:{exc}")
        return receipt
    if len(parts) < 3 or parts[0] != "docker" or parts[1] != "run":
        receipt["status"] = "FAIL"
        receipt["problems"].append("docker-command-required")
    image = extract_docker_run_image(command)
    if parts[:2] == ["docker", "run"] and not image:
        receipt["status"] = "FAIL"
        receipt["problems"].append("docker-image-required")
    if image:
        receipt["image"] = image
    joined = " ".join(parts)
    for mount in DISALLOWED_MOUNTS:
        if mount in joined:
            receipt["status"] = "FAIL"
            receipt["problems"].append(f"docker-host-escape-mount:{mount}")
    for fragment in DISALLOWED_MOUNT_FRAGMENTS:
        if fragment in joined:
            receipt["status"] = "FAIL"
            receipt["problems"].append(f"docker-credential-mount:{fragment}")
    return receipt
