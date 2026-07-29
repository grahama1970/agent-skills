"""Compile target Docker Compose files through a fail-closed Hack policy.

Inputs are an operator-authorized Compose file and a target authorization
manifest. Outputs are a deterministic sanitized Compose artifact plus a policy
receipt, or a fail-closed receipt with stable rejection codes. The module may
invoke ``docker compose config`` to normalize Compose syntax, but it never
starts containers, builds images, scans networks, or executes target code.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

import typer
from rich.console import Console

from common.security_authorization import file_sha256
from hack.env import load_hack_dotenv as dotenv_helper

SCHEMA = "hack.compose_policy_receipt.v1"
POLICY_VERSION = "hack.compose-policy.v1"
COMPOSE_CONFIG_TIMEOUT_SECONDS = 20

console = Console()
dotenv_helper()


@dataclass(frozen=True)
class ComposePolicyResult:
    """Policy compiler result paths and receipt payload."""

    status: str
    sanitized_compose_path: Path | None
    receipt_path: Path
    receipt: dict[str, Any]


def json_sha256(payload: Any) -> str:
    """Return a stable SHA-256 digest for a JSON-serializable payload."""

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write deterministic JSON with a trailing newline."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_authorization(path: Path) -> dict[str, Any]:
    """Read a security target authorization manifest."""

    return json.loads(path.read_text(encoding="utf-8"))


def sterile_compose_env(empty_env_file: Path) -> dict[str, str]:
    """Return a bounded environment for ``docker compose config``."""

    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "COMPOSE_ENV_FILES": str(empty_env_file),
        "COMPOSE_DISABLE_ENV_FILE": "1",
    }
    docker_config = os.environ.get("DOCKER_CONFIG")
    if docker_config:
        env["DOCKER_CONFIG"] = docker_config
    return env


def normalize_compose_with_docker(
    compose_path: Path,
    *,
    work_dir: Path | None = None,
    env: dict[str, str] | None = None,
    timeout_seconds: int = COMPOSE_CONFIG_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Normalize Compose through ``docker compose config --format json``."""

    compose_path = compose_path.resolve()
    with tempfile.NamedTemporaryFile(prefix="hack-compose-empty-", suffix=".env") as empty_env:
        empty_env_file = Path(empty_env.name)
        command = [
            "docker",
            "compose",
            "--env-file",
            str(empty_env_file),
            "-f",
            str(compose_path),
            "config",
            "--format",
            "json",
        ]
        result = subprocess.run(
            command,
            cwd=work_dir or compose_path.parent,
            env=env or sterile_compose_env(empty_env_file),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    if result.returncode != 0:
        raise RuntimeError(f"docker compose config failed: {result.stderr.strip() or result.stdout.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"docker compose config emitted invalid JSON: {exc}") from exc


def compile_compose_policy(
    *,
    source_compose_path: Path,
    authorization_manifest: Path,
    sanitized_compose_path: Path,
    receipt_out: Path,
    source_root: Path | None = None,
    session_root: Path | None = None,
    compose_env: dict[str, str] | None = None,
    allowed_variable_names: set[str] | None = None,
    normalizer: Callable[[Path], dict[str, Any]] | None = None,
) -> ComposePolicyResult:
    """Compile, evaluate, and materialize a sanitized Compose file."""

    source_compose_path = source_compose_path.resolve()
    sanitized_compose_path = sanitized_compose_path.resolve()
    receipt_out = receipt_out.resolve()
    source_root = (source_root or source_compose_path.parent).resolve()
    session_root = (session_root or sanitized_compose_path.parent).resolve()
    auth = read_authorization(authorization_manifest)
    errors: list[dict[str, str]] = []
    allowed_features: list[str] = []
    normalized_model: dict[str, Any] | None = None
    sanitized_model: dict[str, Any] | None = None
    normalized_hash: str | None = None
    sanitized_hash: str | None = None

    try:
        errors.extend(raw_compose_rejections(source_compose_path, allowed_variable_names=allowed_variable_names or set()))
        normalized_model = normalizer(source_compose_path) if normalizer else normalize_compose_with_docker(source_compose_path, env=compose_env)
        normalized_hash = json_sha256(normalized_model)
        sanitized_model, allowed_features, model_errors = sanitize_compose_model(
            normalized_model,
            source_root=source_root,
            session_root=session_root,
            authorization=auth,
        )
        errors.extend(model_errors)
    except Exception as exc:
        errors.append(
            {
                "code": "COMPOSE_NORMALIZATION_ERROR",
                "message": f"{type(exc).__name__}: {exc}",
                "service": "",
                "field": "",
            }
        )

    status = "PASS" if not errors else "FAIL"
    if status == "PASS" and sanitized_model is not None:
        sanitized_compose_path.parent.mkdir(parents=True, exist_ok=True)
        sanitized_compose_path.write_text(json.dumps(sanitized_model, indent=2, sort_keys=True) + "\n")
        sanitized_hash = file_sha256(sanitized_compose_path)

    receipt = {
        "schema": SCHEMA,
        "policy_version": POLICY_VERSION,
        "status": status,
        "source_compose_path": str(source_compose_path),
        "source_compose_sha256": file_sha256(source_compose_path) if source_compose_path.exists() else None,
        "normalized_model_sha256": normalized_hash,
        "sanitized_compose_path": str(sanitized_compose_path) if status == "PASS" else None,
        "sanitized_compose_sha256": sanitized_hash,
        "authorization_manifest_path": str(authorization_manifest.resolve()),
        "authorization_manifest_sha256": file_sha256(authorization_manifest),
        "allowed_features": sorted(set(allowed_features)),
        "rejected_features": errors,
        "execution_started": False,
        "mocked": False,
        "live": "docker_compose_config" if normalizer is None else "injected_normalized_model",
        "non_claims": [
            "compose_policy_does_not_start_target",
            "compose_policy_does_not_prove_target_safety",
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(receipt_out, receipt)
    return ComposePolicyResult(
        status=status,
        sanitized_compose_path=sanitized_compose_path if status == "PASS" else None,
        receipt_path=receipt_out,
        receipt=receipt,
    )


def sanitize_compose_model(
    model: dict[str, Any],
    *,
    source_root: Path,
    session_root: Path,
    authorization: dict[str, Any],
) -> tuple[dict[str, Any], list[str], list[dict[str, str]]]:
    """Return sanitized Compose plus allowed and rejected feature records."""

    errors: list[dict[str, str]] = []
    allowed: list[str] = []
    services = model.get("services")
    if not isinstance(services, dict) or not services:
        return {"services": {}}, allowed, [reject("", "services", "SERVICES_REQUIRED", "Compose model must define services")]
    sanitized_services: dict[str, Any] = {}
    allowed_ports = {int(port) for port in authorization.get("allowed_ports", []) if isinstance(port, int)}
    for service_name in sorted(services):
        service = services[service_name]
        if not isinstance(service, dict):
            errors.append(reject(service_name, "", "SERVICE_NOT_OBJECT", "service must be an object"))
            continue
        sanitized, service_allowed, service_errors = sanitize_service(
            service_name,
            service,
            source_root=source_root,
            session_root=session_root,
            allowed_ports=allowed_ports,
        )
        allowed.extend(service_allowed)
        errors.extend(service_errors)
        if not service_errors:
            sanitized_services[service_name] = sanitized
    top_networks = model.get("networks")
    if isinstance(top_networks, dict) and set(top_networks) - {"default"}:
        errors.append(reject("", "networks", "UNAPPROVED_TOP_LEVEL_NETWORKS", "only the implicit default network is allowed"))
    elif top_networks not in (None, {}):
        allowed.append("default_network")
    if model.get("secrets"):
        errors.append(reject("", "secrets", "UNAPPROVED_TOP_LEVEL_SECRETS", "top-level secrets are not allowed"))
    if model.get("configs"):
        errors.append(reject("", "configs", "UNAPPROVED_TOP_LEVEL_CONFIGS", "top-level configs are not allowed"))
    return {"services": sanitized_services}, allowed, errors


def raw_compose_rejections(compose_path: Path, *, allowed_variable_names: set[str] | None = None) -> list[dict[str, str]]:
    """Reject source constructs that Compose normalization can erase."""

    allowed_variable_names = allowed_variable_names or set()
    text = compose_path.read_text(encoding="utf-8", errors="replace")
    checks = {
        "env_file": "ENV_FILE_DENIED",
        "secrets": "RAW_SECRETS_DENIED",
        "configs": "RAW_CONFIGS_DENIED",
    }
    errors: list[dict[str, str]] = []
    for key, code in checks.items():
        if re_search_key(text, key):
            errors.append(reject("", key, code, f"{key} is denied before Compose normalization"))
    for variable in sorted(extract_variable_references(text) - allowed_variable_names):
        errors.append(reject("", "interpolation", "UNDECLARED_VARIABLE_REFERENCE", f"{variable} is not declared for target Compose interpolation"))
    return errors


def extract_variable_references(text: str) -> set[str]:
    """Return Compose-style ``${VAR}`` interpolation references."""

    refs: set[str] = set()
    for match in re.finditer(r"\$\{([^}:?+-]+)(?::?[-+?][^}]*)?\}", text):
        refs.add(match.group(1))
    return refs


def re_search_key(text: str, key: str) -> bool:
    """Return whether a YAML key appears at a line start."""

    marker = f"{key}:"
    return any(line.strip().startswith(marker) for line in text.splitlines())


def sanitize_service(
    service_name: str,
    service: dict[str, Any],
    *,
    source_root: Path,
    session_root: Path,
    allowed_ports: set[int],
) -> tuple[dict[str, Any], list[str], list[dict[str, str]]]:
    """Validate one service and return its sanitized representation."""

    allowed_service_keys = {
        "image",
        "build",
        "command",
        "entrypoint",
        "environment",
        "ports",
        "volumes",
        "working_dir",
        "user",
        "healthcheck",
        "depends_on",
        "restart",
        "labels",
        "container_name",
        "networks",
    }
    namespace_keys = ("network_mode", "pid", "ipc", "uts", "cgroup", "userns_mode")
    hard_denied = {
        "privileged": "PRIVILEGED_DENIED",
        "cap_add": "CAP_ADD_DENIED",
        "devices": "DEVICES_DENIED",
        "security_opt": "SECURITY_OPT_DENIED",
        "sysctls": "SYSCTLS_DENIED",
        "extra_hosts": "EXTRA_HOSTS_DENIED",
        "dns": "DNS_DENIED",
        "dns_search": "DNS_DENIED",
        "secrets": "SERVICE_SECRETS_DENIED",
        "configs": "SERVICE_CONFIGS_DENIED",
    }
    errors: list[dict[str, str]] = []
    allowed: list[str] = []
    sanitized: dict[str, Any] = {}
    for key in sorted(set(service) - allowed_service_keys - set(namespace_keys) - set(hard_denied)):
        errors.append(reject(service_name, key, "UNSUPPORTED_SERVICE_FIELD", "unsupported Compose service field"))
    for key, code in hard_denied.items():
        if key in service and service.get(key) not in (None, [], {}, False):
            errors.append(reject(service_name, key, code, f"{key} is not allowed"))
    for key in namespace_keys:
        if key in service and service.get(key) not in (None, "", "bridge"):
            errors.append(reject(service_name, key, "HOST_NAMESPACE_DENIED", f"{key} is not allowed"))
    if service.get("image"):
        sanitized["image"] = service["image"]
        allowed.append("image")
    if service.get("build") is not None:
        build = sanitize_build(service_name, service["build"], source_root=source_root, errors=errors)
        if build is not None:
            sanitized["build"] = build
            allowed.append("build")
    for key in ("command", "entrypoint", "environment", "working_dir", "user", "healthcheck", "depends_on", "restart", "labels", "container_name"):
        if key in service:
            sanitized[key] = service[key]
            allowed.append(key)
    if "networks" in service:
        networks = service["networks"]
        if isinstance(networks, dict) and set(networks) <= {"default"}:
            allowed.append("default_network")
        elif networks not in (None, {}, []):
            errors.append(reject(service_name, "networks", "UNAPPROVED_SERVICE_NETWORKS", "only the implicit default network is allowed"))
    if "ports" in service:
        ports, port_errors = sanitize_ports(service_name, service["ports"], allowed_ports=allowed_ports)
        errors.extend(port_errors)
        if ports:
            sanitized["ports"] = ports
            allowed.append("loopback_ports")
    if "volumes" in service:
        volumes, volume_errors = sanitize_volumes(
            service_name,
            service["volumes"],
            source_root=source_root,
            session_root=session_root,
        )
        errors.extend(volume_errors)
        if volumes:
            sanitized["volumes"] = volumes
            allowed.append("bounded_bind_mounts")
    if "image" not in sanitized and "build" not in sanitized:
        errors.append(reject(service_name, "image", "IMAGE_OR_BUILD_REQUIRED", "service must define image or build"))
    return sanitized, allowed, errors


def sanitize_build(service_name: str, build: Any, *, source_root: Path, errors: list[dict[str, str]]) -> Any:
    """Validate build context and dockerfile paths."""

    if isinstance(build, str):
        context = resolve_under_root(build, source_root)
        if context is None:
            errors.append(reject(service_name, "build.context", "BUILD_CONTEXT_OUTSIDE_ROOT", "build context escapes source root"))
            return None
        return {"context": str(context)}
    if not isinstance(build, dict):
        errors.append(reject(service_name, "build", "BUILD_INVALID", "build must be string or object"))
        return None
    context_value = str(build.get("context", "."))
    context = resolve_under_root(context_value, source_root)
    if context is None:
        errors.append(reject(service_name, "build.context", "BUILD_CONTEXT_OUTSIDE_ROOT", "build context escapes source root"))
        return None
    sanitized = {"context": str(context)}
    dockerfile_value = build.get("dockerfile")
    if dockerfile_value:
        dockerfile = (context / str(dockerfile_value)).resolve()
        if not is_relative_to(dockerfile, context):
            errors.append(reject(service_name, "build.dockerfile", "DOCKERFILE_OUTSIDE_CONTEXT", "Dockerfile escapes build context"))
            return None
        sanitized["dockerfile"] = str(dockerfile.relative_to(context))
    return sanitized


def sanitize_ports(service_name: str, ports: Any, *, allowed_ports: set[int]) -> tuple[list[Any], list[dict[str, str]]]:
    """Permit only loopback published ports authorized by manifest."""

    errors: list[dict[str, str]] = []
    sanitized: list[Any] = []
    if not isinstance(ports, list):
        return sanitized, [reject(service_name, "ports", "PORTS_INVALID", "ports must be an array")]
    for index, port in enumerate(ports):
        field = f"ports[{index}]"
        host_ip: str | None = None
        published: int | None = None
        target: int | None = None
        if isinstance(port, str):
            parts = port.split(":")
            if len(parts) == 3:
                host_ip, published_text, target_text = parts
            elif len(parts) == 2:
                published_text, target_text = parts
                host_ip = "127.0.0.1"
            else:
                errors.append(reject(service_name, field, "PORT_FORMAT_DENIED", "ports must publish explicit loopback host and target ports"))
                continue
            published = parse_port(published_text)
            target = parse_port(target_text)
        elif isinstance(port, dict):
            host_ip = str(port.get("host_ip") or "127.0.0.1")
            published = parse_port(port.get("published"))
            target = parse_port(port.get("target"))
        else:
            errors.append(reject(service_name, field, "PORT_FORMAT_DENIED", "port entry must be string or object"))
            continue
        if host_ip not in {"127.0.0.1", "localhost"}:
            errors.append(reject(service_name, field, "NON_LOOPBACK_PORT_DENIED", "published ports must bind loopback"))
            continue
        if published not in allowed_ports or target not in allowed_ports:
            errors.append(reject(service_name, field, "PORT_NOT_AUTHORIZED", "published and target ports must be authorized"))
            continue
        sanitized.append({"mode": "ingress", "host_ip": "127.0.0.1", "published": published, "target": target, "protocol": "tcp"})
    return sanitized, errors


def sanitize_volumes(
    service_name: str,
    volumes: Any,
    *,
    source_root: Path,
    session_root: Path,
) -> tuple[list[Any], list[dict[str, str]]]:
    """Permit bounded bind mounts and reject sockets or writable source mounts."""

    errors: list[dict[str, str]] = []
    sanitized: list[Any] = []
    if not isinstance(volumes, list):
        return sanitized, [reject(service_name, "volumes", "VOLUMES_INVALID", "volumes must be an array")]
    for index, volume in enumerate(volumes):
        field = f"volumes[{index}]"
        parsed = parse_volume(volume)
        if parsed is None:
            errors.append(reject(service_name, field, "VOLUME_FORMAT_DENIED", "volume must be a bind mount with source and target"))
            continue
        source, target, read_only = parsed
        if is_container_socket_path(source) or is_container_socket_path(target):
            errors.append(reject(service_name, field, "CONTAINER_SOCKET_MOUNT_DENIED", "Docker/Podman socket mounts are denied"))
            continue
        source_path = Path(source).expanduser()
        if not source_path.is_absolute():
            source_path = (source_root / source).resolve()
        else:
            source_path = source_path.resolve()
        if not (is_relative_to(source_path, source_root) or is_relative_to(source_path, session_root)):
            errors.append(reject(service_name, field, "HOST_BIND_OUTSIDE_ROOT", "bind mount source escapes approved roots"))
            continue
        if is_relative_to(source_path, source_root) and not read_only:
            errors.append(reject(service_name, field, "SOURCE_BIND_WRITABLE_DENIED", "source-root binds must be read-only"))
            continue
        sanitized.append({"type": "bind", "source": str(source_path), "target": target, "read_only": read_only})
    return sanitized, errors


def parse_volume(volume: Any) -> tuple[str, str, bool] | None:
    """Parse a Compose volume entry into source, target, read-only."""

    if isinstance(volume, str):
        parts = volume.split(":")
        if len(parts) < 2:
            return None
        return parts[0], parts[1], len(parts) >= 3 and parts[2] in {"ro", "readonly"}
    if isinstance(volume, dict):
        if volume.get("type", "bind") != "bind":
            return None
        source = volume.get("source")
        target = volume.get("target")
        if not source or not target:
            return None
        return str(source), str(target), bool(volume.get("read_only") or volume.get("readonly"))
    return None


def parse_port(value: Any) -> int | None:
    """Return an integer TCP port from Compose string/int values."""

    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def resolve_under_root(value: str, root: Path) -> Path | None:
    """Resolve a path and ensure it stays under root."""

    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    return resolved if is_relative_to(resolved, root) else None


def is_relative_to(path: Path, root: Path) -> bool:
    """Return whether path is equal to or inside root."""

    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def is_container_socket_path(value: str) -> bool:
    """Return whether a path names a Docker or Podman control socket."""

    lowered = value.lower()
    return "docker.sock" in lowered or "podman.sock" in lowered or "/var/run/docker" in lowered


def reject(service: str, field: str, code: str, message: str) -> dict[str, str]:
    """Build a stable rejected-feature record."""

    return {"service": service, "field": field, "code": code, "message": message}


def mark_execution_started(receipt_path: Path) -> None:
    """Update a PASS receipt when session-audit starts Docker compose up."""

    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["execution_started"] = True
    payload["execution_started_at"] = datetime.now(timezone.utc).isoformat()
    write_json(receipt_path, payload)


def create_compose_policy_command() -> Callable[..., None]:
    """Create the Typer command for one Compose policy compilation."""

    def compose_policy(
        compose_file: Path = typer.Argument(..., help="Target Compose file to normalize and sanitize."),
        authorization_manifest: Path = typer.Option(..., "--authorization-manifest"),
        out: Path = typer.Option(..., "--out", help="Sanitized Compose artifact path."),
        receipt_out: Path = typer.Option(..., "--receipt-out", help="Policy receipt output path."),
        source_root: Path | None = typer.Option(None, "--source-root"),
        session_root: Path | None = typer.Option(None, "--session-root"),
    ) -> None:
        """Compile a target Compose file through Hack's fail-closed policy."""

        result = compile_compose_policy(
            source_compose_path=compose_file,
            authorization_manifest=authorization_manifest,
            sanitized_compose_path=out,
            receipt_out=receipt_out,
            source_root=source_root,
            session_root=session_root,
        )
        color = "green" if result.status == "PASS" else "red"
        console.print(f"[{color}]Compose policy {result.status}[/{color}]: {result.receipt_path}")
        if result.status != "PASS":
            raise typer.Exit(1)

    return compose_policy


def create_compose_policy_matrix_command() -> Callable[..., None]:
    """Create the Typer command for malicious fixture matrix receipts."""

    def compose_policy_matrix(
        fixtures_dir: Path = typer.Argument(..., help="Directory containing malicious Compose fixtures."),
        authorization_manifest: Path = typer.Option(..., "--authorization-manifest"),
        out: Path = typer.Option(..., "--out", help="Directory for matrix receipts."),
    ) -> None:
        """Run policy compilation against every fixture and summarize rejections."""

        out.mkdir(parents=True, exist_ok=True)
        cases: list[dict[str, Any]] = []
        docker_up_call_count = 0
        for compose_file in sorted(fixtures_dir.glob("*.yml")):
            case_dir = out / compose_file.stem
            receipt_path = case_dir / "receipt.json"
            sanitized_path = case_dir / "sanitized-compose.yml"
            result = compile_compose_policy(
                source_compose_path=compose_file,
                authorization_manifest=authorization_manifest,
                sanitized_compose_path=sanitized_path,
                receipt_out=receipt_path,
                source_root=compose_file.parent,
                session_root=case_dir,
            )
            cases.append(
                {
                    "fixture": str(compose_file),
                    "status": result.status,
                    "receipt": str(receipt_path),
                    "rejected_codes": [item["code"] for item in result.receipt["rejected_features"]],
                }
            )
        summary = {
            "schema": "hack.compose_policy_matrix.v1",
            "status": "PASS" if cases and all(case["status"] == "FAIL" for case in cases) else "FAIL",
            "case_count": len(cases),
            "docker_up_call_count": docker_up_call_count,
            "cases": cases,
            "mocked": False,
            "live": "docker_compose_config",
        }
        write_json(out / "matrix-summary.json", summary)
        console.print(f"[green]Compose policy matrix:[/green] {out / 'matrix-summary.json'}")
        if summary["status"] != "PASS":
            raise typer.Exit(1)

    return compose_policy_matrix
