"""Build and prove sterile target-runtime environments for Hack.

The target environment is separate from Hack's control plane. It starts from an
empty map and adds only generated, non-secret values needed by an authorized
local scenario. Receipts record hashes and allowlisted names without storing
secret-bearing operator environment values.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

import typer
from rich.console import Console

from common.security_authorization import file_sha256
from hack.compose_policy import compile_compose_policy, extract_variable_references, normalize_compose_with_docker
from hack.env import load_hack_dotenv as dotenv_helper

SCHEMA = "hack.target_environment_receipt.v1"
PROOF_SCHEMA = "hack.sterile_target_environment_proof.v1"
ENVIRONMENT_VERSION = "hack.target-environment.v1"
TARGET_ENV_ALLOWLIST = {
    "PATH",
    "HOME",
    "OPENCLAW_CONFIG_DIR",
    "OPENCLAW_WORKSPACE_DIR",
    "OPENCLAW_GATEWAY_PORT",
    "OPENCLAW_BRIDGE_PORT",
    "OPENCLAW_GATEWAY_HOST",
    "OPENCLAW_GATEWAY_BIND",
    "OPENCLAW_HACK_HARDENING_VALIDATION",
    "HACK_TARGET_STATE_DIR",
}
SECRET_NAME_MARKERS = ("SECRET", "TOKEN", "API_KEY", "PASSWORD", "CREDENTIAL", "PRIVATE_KEY")

console = Console()
dotenv_helper()


def json_sha256(payload: Any) -> str:
    """Return a stable SHA-256 digest for a JSON-serializable payload."""

    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write deterministic JSON with a trailing newline."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def build_sterile_target_environment(
    *,
    session_dir: Path,
    gateway_port: str,
    inherited_environment: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Return an allowlisted target Compose environment and metadata."""

    inherited_environment = inherited_environment or {}
    target_state = session_dir / "target-state"
    home_dir = target_state / "home"
    config_dir = target_state / "config"
    workspace_dir = target_state / "workspace"
    for directory in (home_dir, config_dir, workspace_dir):
        directory.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home_dir),
        "OPENCLAW_CONFIG_DIR": str(config_dir),
        "OPENCLAW_WORKSPACE_DIR": str(workspace_dir),
        "OPENCLAW_GATEWAY_PORT": gateway_port,
        "OPENCLAW_BRIDGE_PORT": str(int(gateway_port) + 1) if gateway_port.isdigit() else "18790",
        "OPENCLAW_GATEWAY_HOST": "127.0.0.1",
        "OPENCLAW_GATEWAY_BIND": "lan",
        "OPENCLAW_HACK_HARDENING_VALIDATION": "1",
        "HACK_TARGET_STATE_DIR": str(target_state),
    }
    unexpected = sorted(set(env) - TARGET_ENV_ALLOWLIST)
    if unexpected:
        raise ValueError(f"target environment contains non-allowlisted keys: {unexpected}")
    metadata = {
        "allowlisted_variable_names": sorted(env),
        "generated_value_hashes": {
            key: sha256(value.encode("utf-8")).hexdigest()
            for key, value in env.items()
            if key != "PATH"
        },
        "inherited_operator_environment": False,
        "operator_secret_names_present": sorted(
            name for name in inherited_environment if is_secret_name(name)
        ),
    }
    return env, metadata


def is_secret_name(name: str) -> bool:
    """Return whether an environment variable name looks secret-bearing."""

    upper = name.upper()
    return any(marker in upper for marker in SECRET_NAME_MARKERS)


def redaction_pairs(environment: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """Return secret name/value pairs that must not be written to logs."""

    environment = environment or os.environ
    pairs: list[tuple[str, str]] = []
    for name, value in environment.items():
        if is_secret_name(name):
            pairs.append((name, value))
    return pairs


def redact_text(text: str, pairs: list[tuple[str, str]] | None = None) -> tuple[str, int]:
    """Redact secret-looking names and values from text."""

    pairs = pairs or redaction_pairs()
    redacted = text
    count = 0
    for name, value in pairs:
        if name and name in redacted:
            redacted = redacted.replace(name, "[REDACTED_SECRET_NAME]")
            count += 1
        if value and value in redacted:
            redacted = redacted.replace(value, "[REDACTED_SECRET_VALUE]")
            count += 1
    return redacted, count


def write_target_environment_receipt(
    *,
    receipt_out: Path,
    authorization_manifest: Path,
    sanitized_compose_path: Path,
    compose_source_path: Path,
    target_env: dict[str, str],
    metadata: dict[str, Any],
    rejected_variable_references: list[str],
    redaction_count: int,
) -> dict[str, Any]:
    """Persist ``hack.target_environment_receipt.v1``."""

    sanitized_exists = sanitized_compose_path.exists()
    payload = {
        "schema": SCHEMA,
        "environment_version": ENVIRONMENT_VERSION,
        "status": "PASS" if not rejected_variable_references else "FAIL",
        "authorization_manifest_sha256": file_sha256(authorization_manifest),
        "sanitized_compose_path": str(sanitized_compose_path.resolve()),
        "sanitized_compose_sha256": file_sha256(sanitized_compose_path) if sanitized_exists else None,
        "compose_source_path": str(compose_source_path.resolve()),
        "compose_source_sha256": file_sha256(compose_source_path),
        "allowlisted_variable_names": sorted(target_env),
        "generated_value_hashes": metadata["generated_value_hashes"],
        "rejected_variable_references": rejected_variable_references,
        "redaction_count": redaction_count,
        "inherited_operator_environment": False,
        "mocked": False,
        "live": "local_docker_compose_sterile_environment" if sanitized_exists else "target_environment_builder",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(receipt_out, payload)
    return payload


def create_prove_sterile_target_environment_command() -> Callable[..., None]:
    """Create the Typer command for the live sterile target env proof."""

    def prove_sterile_target_environment(
        authorization_manifest: Path = typer.Option(..., "--authorization-manifest"),
        compose: Path = typer.Option(..., "--compose"),
        out: Path = typer.Option(..., "--out"),
    ) -> None:
        """Run a live local Docker Compose proof with sentinel secret checks."""

        proof = run_sterile_target_environment_proof(
            authorization_manifest=authorization_manifest,
            compose_path=compose,
            out=out,
        )
        color = "green" if proof["status"] == "PASS" else "red"
        console.print(f"[{color}]Sterile target environment {proof['status']}[/{color}]: {out / 'target-environment-proof.json'}")
        if proof["status"] != "PASS":
            raise typer.Exit(1)

    return prove_sterile_target_environment


def run_sterile_target_environment_proof(
    *,
    authorization_manifest: Path,
    compose_path: Path,
    out: Path,
) -> dict[str, Any]:
    """Compile a fixture Compose file, run it, and assert sentinel isolation."""

    out.mkdir(parents=True, exist_ok=True)
    target_env, metadata = build_sterile_target_environment(
        session_dir=out,
        gateway_port="80",
        inherited_environment=dict(os.environ),
    )
    state_config = out / "target-state" / "config" / "sterile-proof.json"
    write_json(
        state_config,
        {
            "schema": "hack.sterile_target_environment_state_fixture.v1",
            "OPENCLAW_GATEWAY_PORT": target_env["OPENCLAW_GATEWAY_PORT"],
            "OPENCLAW_GATEWAY_HOST": target_env["OPENCLAW_GATEWAY_HOST"],
        },
    )
    text = compose_path.read_text(encoding="utf-8", errors="replace")
    refs = extract_variable_references(text)
    rejected_refs = sorted(refs - set(target_env))
    sanitized = out / "sanitized-compose.yml"
    policy_receipt = out / "compose-policy-receipt.json"
    policy_result = compile_compose_policy(
        source_compose_path=compose_path,
        authorization_manifest=authorization_manifest,
        sanitized_compose_path=sanitized,
        receipt_out=policy_receipt,
        source_root=compose_path.parent,
        session_root=out,
        compose_env=target_env,
        allowed_variable_names=set(target_env),
    )
    redacted_stdout, redaction_count = "", 0
    container_env: dict[str, str] = {}
    command_result: dict[str, Any] = {"returncode": None, "stdout": "", "stderr": ""}
    if policy_result.status == "PASS" and not rejected_refs:
        normalized = normalize_compose_with_docker(compose_path, env=target_env)
        write_json(out / "normalized-compose.json", normalized)
        command = [
            "docker",
            "compose",
            "-f",
            str(sanitized),
            "run",
            "--rm",
            "envcheck",
        ]
        result = subprocess.run(
            command,
            cwd=out,
            env=target_env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        redacted_stdout, stdout_redactions = redact_text(result.stdout)
        redacted_stderr, stderr_redactions = redact_text(result.stderr)
        redaction_count += stdout_redactions + stderr_redactions
        (out / "target-container-env.stdout.log").write_text(redacted_stdout)
        (out / "target-container-env.stderr.log").write_text(redacted_stderr)
        command_result = {
            "command": command,
            "returncode": result.returncode,
            "stdout_log": str(out / "target-container-env.stdout.log"),
            "stderr_log": str(out / "target-container-env.stderr.log"),
        }
        if result.returncode == 0:
            container_env = parse_env_output(result.stdout)
            write_json(out / "target-container-env.json", container_env)
    receipt = write_target_environment_receipt(
        receipt_out=out / "target-environment-receipt.json",
        authorization_manifest=authorization_manifest,
        sanitized_compose_path=sanitized,
        compose_source_path=compose_path,
        target_env=target_env,
        metadata=metadata,
        rejected_variable_references=rejected_refs,
        redaction_count=redaction_count,
    )
    sentinel_values = [
        os.environ.get("HACK_TEST_SECRET", ""),
        os.environ.get("OPENAI_API_KEY", ""),
        os.environ.get("GITHUB_TOKEN", ""),
        os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
    ]
    artifacts = [
        out / "normalized-compose.json",
        sanitized,
        policy_receipt,
        out / "target-environment-receipt.json",
        out / "target-container-env.stdout.log",
        out / "target-container-env.stderr.log",
        out / "target-container-env.json",
        state_config,
    ]
    sentinel_checks = check_sentinels(artifacts, sentinel_values)
    required_reached = {
        key: container_env.get(key)
        for key in ("OPENCLAW_GATEWAY_PORT", "OPENCLAW_CONFIG_DIR", "OPENCLAW_WORKSPACE_DIR")
    }
    status = "PASS"
    errors: list[str] = []
    if policy_result.status != "PASS":
        status = "FAIL"
        errors.append("compose policy failed")
    if rejected_refs:
        status = "FAIL"
        errors.append("compose requested undeclared variables")
    if command_result["returncode"] != 0:
        status = "FAIL"
        errors.append("target env container did not exit zero")
    if any(not item["absent"] for item in sentinel_checks):
        status = "FAIL"
        errors.append("sentinel leaked into proof artifact")
    if not all(required_reached.values()):
        status = "FAIL"
        errors.append("required generated values did not reach target container")
    proof = {
        "schema": PROOF_SCHEMA,
        "status": status,
        "mocked": False,
        "live": "local_docker_compose_run",
        "safe_fixture_container": "envcheck",
        "compose_policy_receipt": str(policy_receipt),
        "target_environment_receipt": str(out / "target-environment-receipt.json"),
        "target_environment_receipt_sha256": file_sha256(out / "target-environment-receipt.json"),
        "sanitized_compose": str(sanitized),
        "sanitized_compose_sha256": file_sha256(sanitized) if sanitized.exists() else None,
        "target_container_env": str(out / "target-container-env.json"),
        "normalized_compose": str(out / "normalized-compose.json"),
        "target_state_config": str(state_config),
        "command_result": command_result,
        "sentinel_checks": sentinel_checks,
        "required_generated_values_reached": required_reached,
        "receipt_status": receipt["status"],
        "errors": errors,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(out / "target-environment-proof.json", proof)
    return proof


def parse_env_output(output: str) -> dict[str, str]:
    """Parse ``env`` command output."""

    env: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", maxsplit=1)
            env[key] = value
    return env


def check_sentinels(paths: list[Path], sentinel_values: list[str]) -> list[dict[str, Any]]:
    """Check that sentinel names and non-empty values are absent from artifacts."""

    needles = ["OPENAI_API_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "HACK_TEST_SECRET"]
    needles.extend(value for value in sentinel_values if value)
    checks: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        present = sorted({needle for needle in needles if needle and needle in text})
        checks.append({"path": str(path), "absent": not present, "present": present})
    return checks
