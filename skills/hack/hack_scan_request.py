"""Validate Dogpile-to-Hack scan request packets without starting execution.

Inputs are JSON files using ``dogpile.hack_scan_request.v1``. Outputs are
``hack.scan_request_validation_receipt.v1`` receipts with target, hash, evidence,
and non-claim metadata. Failure modes are explicit receipt errors; this module
does not import Docker helpers, launch subprocesses, open sockets, or run scans.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

import typer
from rich.console import Console

REQUEST_SCHEMA = "dogpile.hack_scan_request.v1"
RECEIPT_SCHEMA = "hack.scan_request_validation_receipt.v1"
VALIDATOR_VERSION = "hack.scan-request-validator.v1"
EXECUTION_MODE = "no_docker_validation_only"
REQUIRED_NON_CLAIMS = {
    "research_design_input_only",
    "no_scan_executed",
    "no_docker_invoked",
    "no_authorization_proof",
    "no_exploit_or_patch_proof",
}
ALLOWED_SCAN_LANES = {
    "sast",
    "sca",
    "dast",
    "dependency_review",
    "repository_static_review",
    "config_review",
}
ALLOWED_TOP_LEVEL_KEYS = {
    "schema",
    "request_id",
    "created_at",
    "expires_at",
    "target",
    "source_packet",
    "selected_source_evidence",
    "requested_scan",
    "execution_mode",
    "non_claims",
}
ALLOWED_TARGET_KEYS = {"kind", "canonical_id", "immutable_ref", "target_url"}
ALLOWED_SOURCE_PACKET_KEYS = {"schema", "artifact_path", "sha256"}
ALLOWED_EVIDENCE_KEYS = {
    "evidence_id",
    "provider",
    "source_type",
    "url",
    "repository",
    "repository_ref",
    "retrieval_artifact",
    "content_sha256",
    "retrieved_at",
    "source_bearing",
}
ALLOWED_REQUESTED_SCAN_KEYS = {"lanes", "profile"}

console = Console()


def sha256_file(path: Path) -> str:
    """Return a SHA-256 hex digest for a local file."""
    return sha256(path.read_bytes()).hexdigest()


def _json_file_sha256(path: Path) -> str | None:
    try:
        return sha256_file(path)
    except OSError:
        return None


def _resolve_artifact(base_dir: Path, raw_path: Any) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = base_dir / path
    return path


def _parse_time(value: Any, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty ISO-8601 timestamp")
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
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


def _target_identity(target: Any) -> str | None:
    if not isinstance(target, dict):
        return None
    canonical_id = target.get("canonical_id")
    immutable_ref = target.get("immutable_ref")
    if not isinstance(canonical_id, str) or not canonical_id.strip():
        return None
    if not isinstance(immutable_ref, str) or not immutable_ref.strip():
        return None
    return f"{canonical_id}@{immutable_ref}"


def _validate_target(target: Any, errors: list[str]) -> str | None:
    if not isinstance(target, dict):
        errors.append("target must be an object")
        return None
    errors.extend(_unknown_key_errors(target, ALLOWED_TARGET_KEYS, "target"))
    for field in ("kind", "canonical_id", "immutable_ref"):
        if not isinstance(target.get(field), str) or not target.get(field, "").strip():
            errors.append(f"target.{field} is required")
    if "target_url" in target and target.get("target_url") is not None and not isinstance(target.get("target_url"), str):
        errors.append("target.target_url must be a string when present")
    return _target_identity(target)


def _validate_source_packet(
    source_packet: Any,
    *,
    request_dir: Path,
    errors: list[str],
) -> tuple[str | None, str | None, str | None]:
    if not isinstance(source_packet, dict):
        errors.append("source_packet must be an object")
        return None, None, None
    errors.extend(_unknown_key_errors(source_packet, ALLOWED_SOURCE_PACKET_KEYS, "source_packet"))
    schema = source_packet.get("schema")
    if not isinstance(schema, str) or not schema.strip():
        errors.append("source_packet.schema is required")
    artifact_path = _resolve_artifact(request_dir, source_packet.get("artifact_path"))
    expected_sha = source_packet.get("sha256")
    if artifact_path is None:
        errors.append("source_packet.artifact_path is required")
        return schema if isinstance(schema, str) else None, None, None
    if not artifact_path.exists() or not artifact_path.is_file():
        errors.append(f"source_packet.artifact_path does not exist: {artifact_path}")
        return schema if isinstance(schema, str) else None, str(artifact_path), None
    actual_sha = sha256_file(artifact_path)
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        errors.append("source_packet.sha256 is required")
    elif actual_sha != expected_sha:
        errors.append("source_packet.sha256 does not match source packet artifact")
    return schema if isinstance(schema, str) else None, str(artifact_path), actual_sha


def _validate_requested_scan(requested_scan: Any, errors: list[str]) -> None:
    if not isinstance(requested_scan, dict):
        errors.append("requested_scan must be an object")
        return
    errors.extend(_unknown_key_errors(requested_scan, ALLOWED_REQUESTED_SCAN_KEYS, "requested_scan"))
    lanes = requested_scan.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        errors.append("requested_scan.lanes must be a non-empty array")
    else:
        for index, lane in enumerate(lanes):
            if not isinstance(lane, str) or not lane.strip():
                errors.append(f"requested_scan.lanes[{index}] must be a non-empty string")
            elif lane not in ALLOWED_SCAN_LANES:
                errors.append(f"requested_scan.lanes[{index}] has unknown lane: {lane}")
    profile = requested_scan.get("profile")
    if not isinstance(profile, str) or not profile.strip():
        errors.append("requested_scan.profile is required")


def _validate_evidence_item(
    item: Any,
    *,
    index: int,
    request_dir: Path,
    errors: list[str],
) -> bool:
    label = f"selected_source_evidence[{index}]"
    if not isinstance(item, dict):
        errors.append(f"{label} must be an object")
        return False
    errors.extend(_unknown_key_errors(item, ALLOWED_EVIDENCE_KEYS, label))
    for field in ("evidence_id", "provider", "source_type", "retrieval_artifact", "content_sha256", "retrieved_at"):
        if not isinstance(item.get(field), str) or not item.get(field, "").strip():
            errors.append(f"{label}.{field} is required")
    if not (isinstance(item.get("url"), str) and item.get("url", "").strip()) and not (
        isinstance(item.get("repository"), str) and item.get("repository", "").strip()
    ):
        errors.append(f"{label} must include url or repository")
    _parse_time(item.get("retrieved_at"), f"{label}.retrieved_at", errors)
    if item.get("source_bearing") is not True:
        return False
    artifact = _resolve_artifact(request_dir, item.get("retrieval_artifact"))
    if artifact is None:
        return True
    if not artifact.exists() or not artifact.is_file():
        errors.append(f"{label}.retrieval_artifact does not exist: {artifact}")
        return True
    actual_sha = sha256_file(artifact)
    if actual_sha != item.get("content_sha256"):
        errors.append(f"{label}.content_sha256 does not match retrieval_artifact")
    return True


def validate_scan_request(
    request_json: Path,
    *,
    expected_target: str | None = None,
    receipt_out: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate a Dogpile scan request and optionally write a receipt."""
    validation_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    request_path = request_json.resolve()
    errors: list[str] = []
    request_hash = _json_file_sha256(request_path)
    payload: Any = None
    source_packet_schema: str | None = None
    source_packet_path: str | None = None
    source_packet_sha256: str | None = None
    target_identity: str | None = None
    selected_count = 0
    source_bearing_count = 0

    try:
        payload = json.loads(request_path.read_text())
    except Exception as exc:
        errors.append(f"request JSON cannot be read or parsed: {type(exc).__name__}: {exc}")

    if isinstance(payload, dict):
        errors.extend(_unknown_key_errors(payload, ALLOWED_TOP_LEVEL_KEYS, "request"))
        if payload.get("schema") != REQUEST_SCHEMA:
            errors.append(f"schema must equal {REQUEST_SCHEMA}")
        for field in ("request_id", "created_at", "expires_at"):
            if field not in payload:
                errors.append(f"{field} is required")
        _parse_time(payload.get("created_at"), "created_at", errors)
        expires_at = _parse_time(payload.get("expires_at"), "expires_at", errors)
        if expires_at is not None and expires_at <= validation_time:
            errors.append("expires_at is stale or expired")

        target_identity = _validate_target(payload.get("target"), errors)
        if expected_target and target_identity != expected_target:
            errors.append("target identity does not match --expected-target")

        source_packet_schema, source_packet_path, source_packet_sha256 = _validate_source_packet(
            payload.get("source_packet"),
            request_dir=request_path.parent,
            errors=errors,
        )

        evidence = payload.get("selected_source_evidence")
        if not isinstance(evidence, list):
            errors.append("selected_source_evidence must be an array")
        else:
            selected_count = len(evidence)
            for index, item in enumerate(evidence):
                if _validate_evidence_item(item, index=index, request_dir=request_path.parent, errors=errors):
                    source_bearing_count += 1
        if source_bearing_count < 1:
            errors.append("selected_source_evidence must include at least one source_bearing=true record")

        _validate_requested_scan(payload.get("requested_scan"), errors)
        if payload.get("execution_mode") != EXECUTION_MODE:
            errors.append(f"execution_mode must equal {EXECUTION_MODE}")
        non_claims = payload.get("non_claims")
        if not isinstance(non_claims, list):
            errors.append("non_claims must be an array")
        else:
            claim_set = {item for item in non_claims if isinstance(item, str)}
            missing = sorted(REQUIRED_NON_CLAIMS - claim_set)
            if missing:
                errors.append("non_claims missing required entries: " + ", ".join(missing))
    elif payload is not None:
        errors.append("request payload must be a JSON object")

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "validator_version": VALIDATOR_VERSION,
        "status": "FAIL" if errors else "PASS",
        "valid": not errors,
        "request_path": str(request_path),
        "request_sha256": request_hash,
        "target_identity": target_identity,
        "expected_target": expected_target,
        "source_packet_schema": source_packet_schema,
        "source_packet_path": source_packet_path,
        "source_packet_sha256": source_packet_sha256,
        "selected_evidence_count": selected_count,
        "source_bearing_evidence_count": source_bearing_count,
        "validation_time": validation_time.isoformat(),
        "errors": errors,
        "docker_invoked": False,
        "subprocess_invoked": False,
        "network_invoked": False,
        "execution_started": False,
        "non_claims": sorted(REQUIRED_NON_CLAIMS),
    }
    if receipt_out is not None:
        receipt_out.parent.mkdir(parents=True, exist_ok=True)
        receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def create_validate_scan_request_command() -> Callable[..., None]:
    """Create the Typer command for scan-request validation."""

    def validate_scan_request_command(
        request_json: Path = typer.Argument(..., help="dogpile.hack_scan_request.v1 JSON request to validate."),
        expected_target: str | None = typer.Option(None, "--expected-target", help="Expected target identity, formatted canonical_id@immutable_ref."),
        receipt_out: Path | None = typer.Option(None, "--receipt-out", help="Persist hack.scan_request_validation_receipt.v1 JSON."),
        json_output: bool = typer.Option(False, "--json", help="Print the full validation receipt."),
    ) -> None:
        receipt = validate_scan_request(request_json, expected_target=expected_target, receipt_out=receipt_out)
        if json_output:
            console.print(json.dumps(receipt, indent=2, sort_keys=True))
        elif receipt["status"] == "PASS":
            console.print("[green]Scan request validation passed[/green]")
        else:
            console.print("[red]Scan request validation failed[/red]")
            for error in receipt["errors"]:
                console.print(f"- {error}")
        if receipt["status"] != "PASS":
            raise typer.Exit(2)

    return validate_scan_request_command


__all__ = [
    "EXECUTION_MODE",
    "REQUEST_SCHEMA",
    "RECEIPT_SCHEMA",
    "VALIDATOR_VERSION",
    "create_validate_scan_request_command",
    "validate_scan_request",
]
