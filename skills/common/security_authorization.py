"""Validate target authorization manifests before security execution starts.

The validator consumes ``security.target_authorization.v1`` JSON manifests and
emits ``security.target_authorization_validation_receipt.v1`` receipts. It is a
pure preflight helper: failures return explicit errors with ``execution_started``
false, and this module does not import Docker, QEMU, subprocess, or networking
clients.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

SCHEMA = "security.target_authorization.v1"
RECEIPT_SCHEMA = "security.target_authorization_validation_receipt.v1"
VALIDATOR_VERSION = "security.target-authorization-validator.v1"
ALLOWED_TOP_LEVEL_KEYS = {
    "schema",
    "authorization_id",
    "issuer",
    "approver",
    "issued_at",
    "expires_at",
    "target",
    "allowed_target_urls",
    "allowed_cidrs",
    "allowed_ports",
    "runtime_modes",
    "allowed_actions",
    "allowed_probe_classes",
    "denied_probe_classes",
    "network_policy",
    "egress_policy",
    "limits",
    "permissions",
    "artifact_root",
    "redaction_policy",
    "legal_non_opinion_ack",
}
ALLOWED_TARGET_KEYS = {
    "kind",
    "canonical_id",
    "immutable_ref",
    "repository_url",
    "commit",
    "image",
    "digest",
    "firmware_hash",
}
ALLOWED_LIMIT_KEYS = {"requests_per_second", "max_concurrency", "duration_seconds", "cpu", "memory_mb", "storage_mb"}
ALLOWED_PERMISSION_KEYS = {"destructive", "persistence", "credential", "denial_of_service", "nonlocal"}


def file_sha256(path: Path) -> str:
    """Return SHA-256 for a local manifest file."""
    return sha256(path.read_bytes()).hexdigest()


def _parse_time(value: Any, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty ISO-8601 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} must be a valid ISO-8601 timestamp")
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _unknown_key_errors(data: Any, allowed: set[str], label: str) -> list[str]:
    if not isinstance(data, dict):
        return []
    return [f"{label} contains unknown field: {key}" for key in sorted(set(data) - allowed)]


def target_identity(payload: Any) -> str | None:
    """Return canonical_id@immutable_ref for a manifest payload."""
    if not isinstance(payload, dict):
        return None
    target = payload.get("target")
    if not isinstance(target, dict):
        return None
    canonical_id = target.get("canonical_id")
    immutable_ref = target.get("immutable_ref")
    if not isinstance(canonical_id, str) or not canonical_id.strip():
        return None
    if not isinstance(immutable_ref, str) or not immutable_ref.strip():
        return None
    return f"{canonical_id}@{immutable_ref}"


def _validate_string_list(payload: dict[str, Any], field: str, errors: list[str], *, required: bool = True) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list) or (required and not value):
        errors.append(f"{field} must be a non-empty array")
        return []
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{field}[{index}] must be a non-empty string")
        else:
            items.append(item)
    return items


def _validate_target(payload: dict[str, Any], errors: list[str]) -> str | None:
    target = payload.get("target")
    if not isinstance(target, dict):
        errors.append("target must be an object")
        return None
    errors.extend(_unknown_key_errors(target, ALLOWED_TARGET_KEYS, "target"))
    for field in ("kind", "canonical_id", "immutable_ref"):
        if not isinstance(target.get(field), str) or not target.get(field, "").strip():
            errors.append(f"target.{field} is required")
    return target_identity(payload)


def _validate_limits(payload: dict[str, Any], errors: list[str]) -> None:
    limits = payload.get("limits")
    if not isinstance(limits, dict):
        errors.append("limits must be an object")
        return
    errors.extend(_unknown_key_errors(limits, ALLOWED_LIMIT_KEYS, "limits"))
    for field in ALLOWED_LIMIT_KEYS:
        value = limits.get(field)
        if not isinstance(value, (int, float)) or value <= 0:
            errors.append(f"limits.{field} must be a positive number")


def _validate_permissions(payload: dict[str, Any], errors: list[str]) -> None:
    permissions = payload.get("permissions")
    if not isinstance(permissions, dict):
        errors.append("permissions must be an object")
        return
    errors.extend(_unknown_key_errors(permissions, ALLOWED_PERMISSION_KEYS, "permissions"))
    for field in ALLOWED_PERMISSION_KEYS:
        if not isinstance(permissions.get(field), bool):
            errors.append(f"permissions.{field} must be a JSON boolean")


def validate_target_authorization(
    manifest_path: Path | None,
    *,
    expected_target: str,
    requested_action: str,
    requested_port: int | None = None,
    requested_target_url: str | None = None,
    requested_probe_class: str | None = None,
    requested_runtime_mode: str | None = None,
    expected_manifest_sha256: str | None = None,
    receipt_out: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate a target authorization manifest and optionally write a receipt."""
    validation_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    errors: list[str] = []
    payload: Any = None
    manifest_hash: str | None = None
    resolved_path = str(manifest_path.resolve()) if manifest_path is not None else None
    identity: str | None = None

    if manifest_path is None:
        errors.append("authorization manifest is required")
    else:
        try:
            manifest_hash = file_sha256(manifest_path)
            payload = json.loads(manifest_path.read_text())
        except Exception as exc:
            errors.append(f"authorization manifest cannot be read or parsed: {type(exc).__name__}: {exc}")

    if manifest_hash and expected_manifest_sha256 and manifest_hash != expected_manifest_sha256:
        errors.append("manifest SHA-256 does not match expected hash")

    if isinstance(payload, dict):
        errors.extend(_unknown_key_errors(payload, ALLOWED_TOP_LEVEL_KEYS, "manifest"))
        if payload.get("schema") != SCHEMA:
            errors.append(f"schema must equal {SCHEMA}")
        for field in ("authorization_id", "issuer", "approver", "artifact_root", "redaction_policy", "network_policy", "egress_policy"):
            if not isinstance(payload.get(field), str) or not payload.get(field, "").strip():
                errors.append(f"{field} is required")
        _parse_time(payload.get("issued_at"), "issued_at", errors)
        expires = _parse_time(payload.get("expires_at"), "expires_at", errors)
        if expires is not None and expires <= validation_time:
            errors.append("expires_at is stale or expired")
        if payload.get("legal_non_opinion_ack") is not True:
            errors.append("legal_non_opinion_ack must be true")

        identity = _validate_target(payload, errors)
        if identity != expected_target:
            errors.append("target identity does not match requested target")

        allowed_actions = _validate_string_list(payload, "allowed_actions", errors)
        if requested_action not in allowed_actions:
            errors.append("requested action is not allowed by manifest")
        allowed_ports = payload.get("allowed_ports")
        if not isinstance(allowed_ports, list) or not allowed_ports:
            errors.append("allowed_ports must be a non-empty array")
        else:
            normalized_ports: list[int] = []
            for index, value in enumerate(allowed_ports):
                if not isinstance(value, int) or value <= 0 or value > 65535:
                    errors.append(f"allowed_ports[{index}] must be a TCP port number")
                else:
                    normalized_ports.append(value)
            if requested_port is not None and requested_port not in normalized_ports:
                errors.append("requested port is not allowed by manifest")
        allowed_urls = _validate_string_list(payload, "allowed_target_urls", errors)
        if requested_target_url and requested_target_url not in allowed_urls:
            errors.append("requested target URL is not allowed by manifest")
        _validate_string_list(payload, "allowed_cidrs", errors)
        runtime_modes = _validate_string_list(payload, "runtime_modes", errors)
        if requested_runtime_mode and requested_runtime_mode not in runtime_modes:
            errors.append("requested runtime mode is not allowed by manifest")
        allowed_probe_classes = _validate_string_list(payload, "allowed_probe_classes", errors)
        denied_probe_classes = _validate_string_list(payload, "denied_probe_classes", errors, required=False)
        if requested_probe_class:
            if requested_probe_class not in allowed_probe_classes:
                errors.append("requested probe class is not allowed by manifest")
            if requested_probe_class in denied_probe_classes:
                errors.append("requested probe class is explicitly denied by manifest")
        _validate_limits(payload, errors)
        _validate_permissions(payload, errors)
    elif payload is not None:
        errors.append("authorization manifest payload must be a JSON object")

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "validator_version": VALIDATOR_VERSION,
        "status": "FAIL" if errors else "PASS",
        "valid": not errors,
        "manifest_path": resolved_path,
        "manifest_sha256": manifest_hash,
        "target_identity": identity,
        "expected_target": expected_target,
        "requested_action": requested_action,
        "requested_port": requested_port,
        "requested_target_url": requested_target_url,
        "requested_probe_class": requested_probe_class,
        "requested_runtime_mode": requested_runtime_mode,
        "validation_time": validation_time.isoformat(),
        "errors": errors,
        "execution_started": False,
        "docker_invoked": False,
        "qemu_invoked": False,
        "subprocess_invoked": False,
        "network_invoked": False,
        "legal_non_opinion": True,
    }
    if receipt_out is not None:
        receipt_out.parent.mkdir(parents=True, exist_ok=True)
        receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def require_target_authorization(**kwargs: Any) -> dict[str, Any]:
    """Validate authorization and raise ``ValueError`` when it fails."""
    receipt = validate_target_authorization(**kwargs)
    if receipt["status"] != "PASS":
        raise ValueError("; ".join(receipt["errors"]))
    return receipt


__all__ = [
    "RECEIPT_SCHEMA",
    "SCHEMA",
    "VALIDATOR_VERSION",
    "file_sha256",
    "require_target_authorization",
    "target_identity",
    "validate_target_authorization",
]
