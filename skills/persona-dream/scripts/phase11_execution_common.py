#!/usr/bin/env python3
"""Execution-safety helpers for the Persona Dream Phase 11 Fal canary.

The module never submits work during preflight.  It owns approval packet
validation, durable exactly-once fencing, zero-call adapter preflight, and the
small provider-return/download primitives used only by the explicitly gated
``--execute`` path.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator, Mapping, MutableMapping, Sequence

import httpx

from phase11_canonical_common import (
    APPROVAL_FILES,
    APPROVAL_TYPES,
    DEFAULT_OUTPUT_RELATIVE,
    Phase11Blocked,
    approval_bindings,
    build_media_binding_manifest,
    canonical_sha256,
    compile_request_body,
    inspect_approvals,
    load_inputs,
    output_paths,
    parse_time,
    portable_run_path,
    read_object,
    serialized_file_sha256,
    sha256_file,
    upstream_validation_blockers,
    validate_schema,
    write_json,
)

AUTHORIZATION_PURPOSE = "PERSONA_DREAM_PHASE11_SINGLE_KLING_CANARY"
AUTHORIZATION_SCOPE = "ONE_PAID_PROVIDER_GENERATION_NO_AUTOMATIC_RESUBMIT"
ADAPTER_PREFLIGHT_NAME = "phase11_adapter_preflight_receipt.v1.json"
ATTEMPT_LEDGER_NAME = "attempt_ledger.v1.json"
DOWNLOAD_RECEIPT_NAME = "phase11_download_ffprobe_receipt.v1.json"
RETURN_ENVELOPE_NAME = "phase11_provider_return_envelope.v1.json"
DEFAULT_PREFLIGHT_TTL_SECONDS = 3600
MAX_PREFLIGHT_TTL_SECONDS = 3600
MAX_POLL_TIMEOUT_SECONDS = 1800


@dataclass(frozen=True)
class ExecutionState:
    inputs: Any
    request_body: dict[str, Any]
    media_manifest: dict[str, Any]
    bindings: dict[str, Any]
    technical_blockers: tuple[str, ...]
    canonical_paths: dict[str, Path]


@dataclass(frozen=True)
class FalApiSurface:
    module: Any | None
    imported: bool
    version: str | None
    checks: dict[str, bool]
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class SubmitDecision:
    action: str
    request_id: str | None
    ledger: dict[str, Any]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def request_digest(request_body_sha256: str) -> str:
    if not request_body_sha256.startswith("sha256:") or len(request_body_sha256) != 71:
        raise Phase11Blocked("BLOCKED_PHASE11_REQUEST_BODY_HASH_INVALID")
    digest = request_body_sha256.removeprefix("sha256:")
    if any(ch not in "0123456789abcdef" for ch in digest):
        raise Phase11Blocked("BLOCKED_PHASE11_REQUEST_BODY_HASH_INVALID")
    return digest


def attempt_ledger_path(inputs: Any, request_body_sha256: str) -> Path:
    digest = request_digest(request_body_sha256)
    return (
        inputs.context.revision_root
        / "phase_11_submit_return"
        / "attempts"
        / digest
        / ATTEMPT_LEDGER_NAME
    )


def adapter_preflight_path(inputs: Any) -> Path:
    return (
        inputs.context.revision_root
        / "phase_11_submit_return"
        / "preflight"
        / ADAPTER_PREFLIGHT_NAME
    )


def provider_return_root(inputs: Any, request_body_sha256: str) -> Path:
    return (
        inputs.context.revision_root
        / "phase_11_submit_return"
        / "provider_return"
        / request_digest(request_body_sha256)
    )


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def ledger_lock(path: Path) -> Iterator[None]:
    lock_path = path.parent / ".attempt-ledger.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.mkdir(lock_path)
    except FileExistsError as exc:
        raise Phase11Blocked(
            "BLOCKED_PHASE11_ATTEMPT_LEDGER_LOCKED",
            details={"path": str(lock_path)},
        ) from exc
    try:
        yield
    finally:
        try:
            os.rmdir(lock_path)
        except FileNotFoundError:
            pass


def build_execution_state(inputs: Any) -> ExecutionState:
    request_body, request_blockers, _ = compile_request_body(inputs)
    media_manifest = build_media_binding_manifest(inputs, request_body)
    request_body_sha = canonical_sha256(request_body)
    media_manifest_sha = serialized_file_sha256(media_manifest)
    bindings = approval_bindings(
        inputs,
        media_manifest_sha256=media_manifest_sha,
        media_input_contract_sha256=str(media_manifest.get("media_input_contract_sha256") or ""),
        provider_snapshot_sha256=inputs.provider_snapshot.sha256,
        request_body_sha256=request_body_sha,
    )
    blockers = sorted(
        set(
            request_blockers
            + list(media_manifest.get("blockers") or [])
            + upstream_validation_blockers(inputs.validation_path, inputs.context)
        )
    )
    canonical_root = inputs.context.revision_root / DEFAULT_OUTPUT_RELATIVE
    return ExecutionState(
        inputs=inputs,
        request_body=request_body,
        media_manifest=media_manifest,
        bindings=bindings,
        technical_blockers=tuple(blockers),
        canonical_paths=output_paths(canonical_root),
    )


def pricing_maximum(inputs: Any) -> float:
    pricing = inputs.provider_snapshot.value.get("pricing_source")
    if not isinstance(pricing, Mapping):
        raise Phase11Blocked("BLOCKED_PROVIDER_PRICING_CONTRACT")
    try:
        value = float(pricing.get("maximum_expected_cost_usd"))
    except (TypeError, ValueError) as exc:
        raise Phase11Blocked("BLOCKED_PROVIDER_PRICING_CONTRACT") from exc
    if value <= 0:
        raise Phase11Blocked("BLOCKED_PROVIDER_PRICING_CONTRACT")
    return value


def validate_canonical_files(state: ExecutionState) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    values: dict[str, Any] = {}
    for name in ("media_manifest", "approval_requirements", "live_request"):
        path = state.canonical_paths[name]
        if not path.is_file():
            blockers.append(f"BLOCKED_PHASE11_CANONICAL_ARTIFACT_MISSING:{name}")
            continue
        try:
            values[name] = read_object(path)
        except (OSError, ValueError, json.JSONDecodeError):
            blockers.append(f"BLOCKED_PHASE11_CANONICAL_ARTIFACT_INVALID:{name}")
    request = values.get("live_request")
    media = values.get("media_manifest")
    approvals = values.get("approval_requirements")
    if isinstance(request, Mapping):
        if request.get("request_body_sha256") != state.bindings["request_body_sha256"]:
            blockers.append("BLOCKED_PHASE11_REQUEST_BODY_HASH_MISMATCH")
        if request.get("endpoint") != state.bindings["endpoint"]:
            blockers.append("BLOCKED_PHASE11_REQUEST_ENDPOINT_MISMATCH")
    if isinstance(media, Mapping):
        if media.get("media_input_contract_sha256") != state.bindings["media_input_contract_sha256"]:
            blockers.append("BLOCKED_PHASE11_MEDIA_CONTRACT_HASH_MISMATCH")
    if isinstance(approvals, Mapping):
        if approvals.get("bindings") != state.bindings:
            blockers.append("BLOCKED_PHASE11_APPROVAL_BINDINGS_MISMATCH")
    return values, sorted(set(blockers))


def discover_credential(environ: MutableMapping[str, str] | None = None) -> tuple[dict[str, Any], list[str]]:
    env = environ if environ is not None else os.environ
    source: str | None = None
    if env.get("FAL_KEY"):
        source = "FAL_KEY"
    elif env.get("FAL_API_KEY"):
        env["FAL_KEY"] = env["FAL_API_KEY"]
        source = "FAL_API_KEY"
    present = bool(env.get("FAL_KEY"))
    receipt = {
        "present": present,
        "source_variable": source,
        "runtime_variable": "FAL_KEY",
        "secret_value_persisted": False,
        "secret_hash_persisted": False,
    }
    return receipt, [] if present else ["BLOCKED_FAL_CREDENTIAL_MISSING"]


def inspect_fal_api(importer: Callable[[str], Any] = importlib.import_module) -> FalApiSurface:
    try:
        module = importer("fal_client")
        implementation = importer("fal_client.client")
    except Exception as exc:  # import failure is preflight data, never a provider call
        return FalApiSurface(
            module=None,
            imported=False,
            version=None,
            checks={},
            blockers=(f"BLOCKED_FAL_CLIENT_IMPORT:{type(exc).__name__}",),
        )
    sync_client = getattr(module, "SyncClient", None)
    handle = getattr(module, "SyncRequestHandle", None)
    checks = {
        "SyncClient": isinstance(sync_client, type),
        "SyncClient.submit": callable(getattr(sync_client, "submit", None)),
        "SyncClient.get_handle": callable(getattr(sync_client, "get_handle", None)),
        "SyncClient.status": callable(getattr(sync_client, "status", None)),
        "SyncClient.result": callable(getattr(sync_client, "result", None)),
        "SyncRequestHandle.status": callable(getattr(handle, "status", None)),
        "SyncRequestHandle.get": callable(getattr(handle, "get", None)),
        "single_attempt_control": hasattr(implementation, "MAX_ATTEMPTS"),
    }
    blockers = [f"BLOCKED_FAL_CLIENT_API_SURFACE:{name}" for name, passed in checks.items() if not passed]
    return FalApiSurface(
        module=module,
        imported=True,
        version=str(getattr(module, "__version__", "unknown")),
        checks=checks,
        blockers=tuple(sorted(blockers)),
    )


def poll_policy(interval_seconds: float, max_polls: int) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    if not 0.5 <= interval_seconds <= 60:
        blockers.append("BLOCKED_PHASE11_POLL_INTERVAL_OUT_OF_BOUNDS")
    if not 1 <= max_polls <= 360:
        blockers.append("BLOCKED_PHASE11_MAX_POLLS_OUT_OF_BOUNDS")
    timeout_seconds = interval_seconds * max_polls
    if timeout_seconds > MAX_POLL_TIMEOUT_SECONDS:
        blockers.append("BLOCKED_PHASE11_POLL_TIMEOUT_OUT_OF_BOUNDS")
    return {
        "interval_seconds": interval_seconds,
        "max_polls": max_polls,
        "maximum_elapsed_seconds": timeout_seconds,
    }, blockers


def check_download_directory(path: Path) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    relative_path = path
    try:
        path.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".write-probe.", dir=path)
        os.close(fd)
        Path(name).unlink()
    except OSError:
        blockers.append("BLOCKED_PHASE11_DOWNLOAD_DIRECTORY_NOT_WRITABLE")
    return {"path": relative_path, "writable": not blockers}, blockers


def new_preflight_ledger(inputs: Any, request_body_sha256: str, current: datetime) -> dict[str, Any]:
    digest = request_digest(request_body_sha256)
    return {
        "schema": "persona_dream.phase11_attempt_ledger.v1",
        "run_id": inputs.context.run_id,
        "revision_id": inputs.context.revision_id,
        "activation_transaction_id": inputs.context.activation_transaction_id,
        "endpoint": str(inputs.provider_snapshot.value.get("endpoint") or ""),
        "request_key": digest,
        "request_body_sha256": request_body_sha256,
        "state": "PREFLIGHT_READY",
        "submit_intent_count": 0,
        "actual_provider_call_attempts": 0,
        "request_id": None,
        "ambiguous_submit": False,
        "poll_count": 0,
        "created_at": iso(current),
        "updated_at": iso(current),
        "history": [
            {
                "event": "PREFLIGHT_READY",
                "at": iso(current),
                "actual_provider_call_attempts": 0,
            }
        ],
    }


def validate_ledger(ledger: Mapping[str, Any], inputs: Any, request_body_sha256: str) -> list[str]:
    blockers = [f"BLOCKED_PHASE11_ATTEMPT_LEDGER_SCHEMA:{error}" for error in validate_schema(ledger, "phase11_attempt_ledger.v1.schema.json")]
    expected = {
        "run_id": inputs.context.run_id,
        "revision_id": inputs.context.revision_id,
        "activation_transaction_id": inputs.context.activation_transaction_id,
        "endpoint": str(inputs.provider_snapshot.value.get("endpoint") or ""),
        "request_key": request_digest(request_body_sha256),
        "request_body_sha256": request_body_sha256,
    }
    for field, value in expected.items():
        if ledger.get(field) != value:
            blockers.append(f"BLOCKED_PHASE11_ATTEMPT_LEDGER_BINDING:{field}")
    if ledger.get("state") == "SUBMIT_INTENT_WRITTEN" and not ledger.get("request_id"):
        blockers.append("BLOCKED_PHASE11_AMBIGUOUS_SUBMIT_REQUIRES_HUMAN_RECONCILIATION")
    if ledger.get("state") == "AMBIGUOUS_SUBMIT" or ledger.get("ambiguous_submit") is True:
        blockers.append("BLOCKED_PHASE11_AMBIGUOUS_SUBMIT_REQUIRES_HUMAN_RECONCILIATION")
    return sorted(set(blockers))


def ensure_preflight_ledger(inputs: Any, request_body_sha256: str, current: datetime) -> tuple[dict[str, Any], Path, list[str]]:
    path = attempt_ledger_path(inputs, request_body_sha256)
    with ledger_lock(path):
        if path.is_file():
            try:
                ledger = read_object(path)
            except (OSError, ValueError, json.JSONDecodeError):
                return {}, path, ["BLOCKED_PHASE11_ATTEMPT_LEDGER_INVALID"]
        else:
            ledger = new_preflight_ledger(inputs, request_body_sha256, current)
            atomic_write_json(path, ledger)
        blockers = validate_ledger(ledger, inputs, request_body_sha256)
        if ledger.get("state") != "PREFLIGHT_READY" or ledger.get("actual_provider_call_attempts") != 0:
            blockers.append("BLOCKED_PHASE11_ATTEMPT_LEDGER_NOT_PREFLIGHT_READY")
        return ledger, path, sorted(set(blockers))


def preflight_expiry(inputs: Any, current: datetime) -> datetime:
    retrieved = parse_time(str(inputs.provider_snapshot.value.get("retrieved_at") or ""))
    ttl = int(inputs.provider_snapshot.value.get("ttl_seconds") or 0)
    provider_expiry = retrieved + timedelta(seconds=ttl)
    local_expiry = current + timedelta(seconds=DEFAULT_PREFLIGHT_TTL_SECONDS)
    return min(provider_expiry, local_expiry)


def run_adapter_preflight(
    inputs: Any,
    *,
    current: datetime,
    poll_interval_seconds: float,
    max_polls: int,
    adapter_script_path: Path,
    environ: MutableMapping[str, str] | None = None,
    importer: Callable[[str], Any] = importlib.import_module,
    ffprobe_resolver: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    state = build_execution_state(inputs)
    blockers = list(state.technical_blockers)
    _canonical, canonical_blockers = validate_canonical_files(state)
    blockers.extend(canonical_blockers)

    credential, credential_blockers = discover_credential(environ)
    blockers.extend(credential_blockers)
    fal_api = inspect_fal_api(importer)
    blockers.extend(fal_api.blockers)
    ffprobe_path = ffprobe_resolver("ffprobe")
    if not ffprobe_path:
        blockers.append("BLOCKED_PHASE11_FFPROBE_MISSING")
    policy, policy_blockers = poll_policy(poll_interval_seconds, max_polls)
    blockers.extend(policy_blockers)

    ledger, ledger_path, ledger_blockers = ensure_preflight_ledger(
        inputs, state.bindings["request_body_sha256"], current
    )
    blockers.extend(ledger_blockers)
    return_root = provider_return_root(inputs, state.bindings["request_body_sha256"])
    download_state, download_blockers = check_download_directory(return_root)
    blockers.extend(download_blockers)

    approval_statuses, missing_approvals, approval_blockers = inspect_approvals(
        inputs, state.bindings, current
    )
    blockers.extend(approval_blockers)
    try:
        expires_at = preflight_expiry(inputs, current)
    except (TypeError, ValueError):
        blockers.append("BLOCKED_PROVIDER_SOURCE_SNAPSHOT_TIMESTAMP_INVALID")
        expires_at = current

    ledger_ref = {
        "relative_path": portable_run_path(inputs.context, ledger_path),
        "sha256": sha256_file(ledger_path) if ledger_path.is_file() else None,
        "state": ledger.get("state"),
        "request_key": ledger.get("request_key"),
        "submit_intent_count": ledger.get("submit_intent_count"),
        "actual_provider_call_attempts": ledger.get("actual_provider_call_attempts"),
    }
    receipt = {
        "schema": "persona_dream.phase11_adapter_preflight_receipt.v1",
        "status": "PASS_PHASE11_ADAPTER_PREFLIGHT" if not blockers else "BLOCKED_PHASE11_ADAPTER_PREFLIGHT",
        "run_id": inputs.context.run_id,
        "revision_id": inputs.context.revision_id,
        "activation_transaction_id": inputs.context.activation_transaction_id,
        "endpoint": state.bindings["endpoint"],
        "request_body_sha256": state.bindings["request_body_sha256"],
        "media_input_contract_sha256": state.bindings["media_input_contract_sha256"],
        "provider_source_snapshot_sha256": state.bindings["provider_source_snapshot_sha256"],
        "pricing_snapshot_sha256": state.bindings["pricing_snapshot_sha256"],
        "approval_binding_sha256": canonical_sha256(state.bindings),
        "adapter_script_sha256": sha256_file(adapter_script_path),
        "credential": credential,
        "fal_client": {
            "imported": fal_api.imported,
            "version": fal_api.version,
            "api_surface": fal_api.checks,
            "submit_retry_control": "fal_client.client.MAX_ATTEMPTS=1",
        },
        "ffprobe": {"available": bool(ffprobe_path), "path": ffprobe_path},
        "poll_policy": policy,
        "attempt_ledger": ledger_ref,
        "download_directory": {
            "relative_path": portable_run_path(inputs.context, return_root),
            "writable": bool(download_state.get("writable")),
        },
        "approval_validation": {
            "required_types": list(APPROVAL_TYPES),
            "missing_types": missing_approvals,
            "receipts": approval_statuses,
            "invalid_blockers": approval_blockers,
        },
        "idempotency": {
            "fence_written_before_submit": True,
            "existing_task_resumes_without_submit": True,
            "submit_intent_without_task_id_fails_closed": True,
            "ambiguous_submit_requires_human_reconciliation": True,
            "automatic_resubmit_allowed": False,
        },
        "technical_blockers": sorted(set(blockers)),
        "created_at": iso(current),
        "expires_at": iso(expires_at),
        "mocked": bool(inputs.context.mocked),
        "live": not bool(inputs.context.mocked),
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "actual_provider_call_attempts": 0,
    }
    schema_errors = validate_schema(receipt, "phase11_adapter_preflight_receipt.v1.schema.json")
    if schema_errors:
        raise Phase11Blocked(
            "BLOCKED_PHASE11_ADAPTER_PREFLIGHT_RECEIPT_SCHEMA",
            details={"errors": schema_errors},
        )
    write_json(adapter_preflight_path(inputs), receipt)
    return receipt


def approval_packet_receipts(
    inputs: Any,
    packet: Mapping[str, Any],
    *,
    packet_path: Path,
    current: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    errors = validate_schema(packet, "phase11_authorization_packet.v1.schema.json")
    if errors:
        raise Phase11Blocked(
            "BLOCKED_PHASE11_AUTHORIZATION_PACKET_SCHEMA",
            details={"errors": errors},
        )
    state = build_execution_state(inputs)
    if state.technical_blockers:
        raise Phase11Blocked(
            "BLOCKED_PHASE11_AUTHORIZATION_TECHNICAL_GATE",
            details={"blockers": list(state.technical_blockers)},
        )
    expected = {
        "run_id": inputs.context.run_id,
        "revision_id": inputs.context.revision_id,
        "activation_transaction_id": inputs.context.activation_transaction_id,
        "bindings": state.bindings,
        "approval_types": list(APPROVAL_TYPES),
        "purpose": AUTHORIZATION_PURPOSE,
        "authorization_scope": AUTHORIZATION_SCOPE,
        "decision": "APPROVE",
        "decision_source": "EXPLICIT_HUMAN",
        "revoked": False,
        "revocation_state": "NOT_REVOKED",
        "currency": "USD",
    }
    for field, value in expected.items():
        if packet.get(field) != value:
            raise Phase11Blocked(
                f"BLOCKED_PHASE11_AUTHORIZATION_PACKET_BINDING:{field}"
            )
    approved_at = parse_time(str(packet.get("approved_at") or ""))
    expires_at = parse_time(str(packet.get("expires_at") or ""))
    if approved_at > current + timedelta(minutes=5):
        raise Phase11Blocked("BLOCKED_PHASE11_AUTHORIZATION_PACKET_FUTURE")
    if expires_at <= current or expires_at <= approved_at:
        raise Phase11Blocked("BLOCKED_PHASE11_AUTHORIZATION_PACKET_EXPIRED")
    maximum_spend = float(packet.get("maximum_spend_usd") or 0)
    if maximum_spend < pricing_maximum(inputs):
        raise Phase11Blocked(
            "BLOCKED_PHASE11_AUTHORIZATION_MAX_SPEND_TOO_LOW",
            details={"required": pricing_maximum(inputs), "observed": maximum_spend},
        )
    preflight = adapter_preflight_path(inputs)
    if not preflight.is_file():
        raise Phase11Blocked("BLOCKED_PHASE11_ADAPTER_PREFLIGHT_REQUIRED")
    preflight_value = read_object(preflight)
    if preflight_value.get("status") != "PASS_PHASE11_ADAPTER_PREFLIGHT":
        raise Phase11Blocked("BLOCKED_PHASE11_ADAPTER_PREFLIGHT_REQUIRED")

    packet_sha = sha256_file(packet_path)
    approver = packet.get("approver")
    assert isinstance(approver, Mapping)
    receipts: list[dict[str, Any]] = []
    for approval_type in APPROVAL_TYPES:
        if approval_type == "publication_authorization":
            binding_kind = "media_input_contract"
            binding_sha = state.bindings["media_input_contract_sha256"]
        else:
            binding_kind = "phase11_request_bundle"
            binding_sha = canonical_sha256(state.bindings)
        receipts.append(
            {
                "schema": "persona_dream.phase11_approval_receipt.v1",
                "status": "APPROVED",
                "approval_type": approval_type,
                **state.bindings,
                "approved_by": str(approver["id"]),
                "approver": dict(approver),
                "approved_at": iso(approved_at),
                "expires_at": iso(expires_at),
                "decision_source": "explicit_human_authorization_packet",
                "purpose": AUTHORIZATION_PURPOSE,
                "authorization_scope": AUTHORIZATION_SCOPE,
                "currency": "USD",
                "maximum_spend_usd": maximum_spend,
                "revoked": False,
                "revocation_state": "NOT_REVOKED",
                "authorization_packet_path": portable_run_path(inputs.context, packet_path),
                "authorization_packet_sha256": packet_sha,
                "approval_binding_kind": binding_kind,
                "approval_binding_sha256": binding_sha,
                "actual_provider_call_attempts": 0,
            }
        )
    for receipt in receipts:
        receipt_errors = validate_schema(receipt, "phase11_approval_receipt.v1.schema.json")
        if receipt_errors:
            raise Phase11Blocked(
                "BLOCKED_PHASE11_APPROVAL_RECEIPT_SCHEMA",
                details={"approval_type": receipt["approval_type"], "errors": receipt_errors},
            )
    return receipts, state.bindings


def write_approval_receipts(
    inputs: Any,
    packet: Mapping[str, Any],
    *,
    packet_path: Path,
    current: datetime,
    dry_run: bool,
) -> dict[str, Any]:
    receipts, bindings = approval_packet_receipts(
        inputs, packet, packet_path=packet_path, current=current
    )
    expected = {str(receipt["approval_type"]): receipt for receipt in receipts}
    approval_root = inputs.approval_root
    written_now = False

    def validate_existing_set() -> None:
        observed = {path.name for path in approval_root.glob("*_receipt.json")} if approval_root.is_dir() else set()
        expected_names = {APPROVAL_FILES[name] for name in APPROVAL_TYPES}
        if observed != expected_names:
            raise Phase11Blocked(
                "BLOCKED_PHASE11_APPROVAL_RECEIPT_SET_CONFLICT",
                details={"expected": sorted(expected_names), "observed": sorted(observed)},
            )
        for approval_type, receipt in expected.items():
            path = approval_root / APPROVAL_FILES[approval_type]
            if read_object(path) != receipt:
                raise Phase11Blocked(
                    "BLOCKED_PHASE11_APPROVAL_RECEIPT_CONFLICT",
                    details={"approval_type": approval_type, "path": str(path)},
                )

    if not dry_run:
        approval_root.parent.mkdir(parents=True, exist_ok=True)
        if approval_root.exists():
            validate_existing_set()
        else:
            staging = Path(
                tempfile.mkdtemp(
                    prefix=".phase11-approvals.",
                    dir=approval_root.parent,
                )
            )
            try:
                os.chmod(staging, 0o700)
                for approval_type in APPROVAL_TYPES:
                    path = staging / APPROVAL_FILES[approval_type]
                    payload = (
                        json.dumps(
                            expected[approval_type],
                            indent=2,
                            sort_keys=True,
                            ensure_ascii=False,
                        )
                        + "\n"
                    ).encode("utf-8")
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(payload)
                        handle.flush()
                        os.fsync(handle.fileno())
                directory_fd = os.open(staging, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                try:
                    os.rename(staging, approval_root)
                    written_now = True
                except FileExistsError:
                    validate_existing_set()
                parent_fd = os.open(approval_root.parent, os.O_RDONLY)
                try:
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)

    outputs: dict[str, Any] = {}
    for approval_type in APPROVAL_TYPES:
        path = approval_root / APPROVAL_FILES[approval_type]
        outputs[approval_type] = {
            "path": portable_run_path(inputs.context, path),
            "sha256": sha256_file(path) if path.is_file() else canonical_sha256(expected[approval_type]),
            "written": bool(written_now and path.is_file()),
        }
    return {
        "schema": "persona_dream.phase11_approval_write_receipt.v1",
        "status": "PASS_PHASE11_APPROVAL_PACKET_VALIDATED_DRY_RUN" if dry_run else "PASS_PHASE11_APPROVAL_RECEIPTS_WRITTEN",
        "run_id": inputs.context.run_id,
        "revision_id": inputs.context.revision_id,
        "activation_transaction_id": inputs.context.activation_transaction_id,
        "bindings": bindings,
        "approval_receipt_count": 5,
        "outputs": outputs,
        "dry_run": dry_run,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "submitted": False,
    }


def load_ledger(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise Phase11Blocked("BLOCKED_PHASE11_ATTEMPT_LEDGER_MISSING")
    try:
        return read_object(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise Phase11Blocked("BLOCKED_PHASE11_ATTEMPT_LEDGER_INVALID") from exc


def append_history(ledger: dict[str, Any], event: str, current: datetime, **fields: Any) -> None:
    history = ledger.setdefault("history", [])
    if not isinstance(history, list):
        raise Phase11Blocked("BLOCKED_PHASE11_ATTEMPT_LEDGER_INVALID")
    history.append(
        {
            "event": event,
            "at": iso(current),
            "actual_provider_call_attempts": ledger.get("actual_provider_call_attempts", 0),
            **fields,
        }
    )
    ledger["updated_at"] = iso(current)


def submit_once(
    inputs: Any,
    request_body_sha256: str,
    *,
    current: datetime,
    submit: Callable[[], str],
) -> SubmitDecision:
    path = attempt_ledger_path(inputs, request_body_sha256)
    with ledger_lock(path):
        ledger = load_ledger(path)
        blockers = validate_ledger(ledger, inputs, request_body_sha256)
        if blockers:
            raise Phase11Blocked(blockers[0], details={"blockers": blockers})
        request_id = str(ledger.get("request_id") or "")
        if request_id:
            return SubmitDecision("resume_existing_task", request_id, ledger)
        if ledger.get("state") != "PREFLIGHT_READY" or int(ledger.get("submit_intent_count") or 0) != 0:
            raise Phase11Blocked("BLOCKED_PHASE11_DUPLICATE_SUBMIT_PREVENTED")

        ledger["state"] = "SUBMIT_INTENT_WRITTEN"
        ledger["submit_intent_count"] = 1
        ledger["ambiguous_submit"] = False
        append_history(ledger, "SUBMIT_INTENT_WRITTEN", current)
        atomic_write_json(path, ledger)
        try:
            request_id = str(submit() or "").strip()
            if not request_id:
                raise RuntimeError("provider returned no request_id")
        except Exception as exc:
            ledger["state"] = "AMBIGUOUS_SUBMIT"
            ledger["ambiguous_submit"] = True
            ledger["actual_provider_call_attempts"] = 1
            ledger["last_error"] = {
                "type": type(exc).__name__,
                "message": str(exc)[:1000],
            }
            append_history(ledger, "AMBIGUOUS_SUBMIT", current)
            atomic_write_json(path, ledger)
            raise Phase11Blocked(
                "BLOCKED_PHASE11_AMBIGUOUS_SUBMIT_REQUIRES_HUMAN_RECONCILIATION"
            ) from exc

        ledger["state"] = "SUBMITTED"
        ledger["request_id"] = request_id
        ledger["actual_provider_call_attempts"] = 1
        append_history(ledger, "SUBMITTED", current, request_id=request_id)
        atomic_write_json(path, ledger)
        return SubmitDecision("submitted_once", request_id, ledger)


def update_poll_state(
    inputs: Any,
    request_body_sha256: str,
    *,
    state: str,
    current: datetime,
    poll_count: int,
    fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    path = attempt_ledger_path(inputs, request_body_sha256)
    with ledger_lock(path):
        ledger = load_ledger(path)
        if not ledger.get("request_id"):
            raise Phase11Blocked("BLOCKED_PHASE11_ATTEMPT_LEDGER_REQUEST_ID_MISSING")
        ledger["state"] = state
        ledger["poll_count"] = poll_count
        if fields:
            ledger.update(dict(fields))
        append_history(ledger, state, current, poll_count=poll_count)
        atomic_write_json(path, ledger)
        return ledger


def download_provider_video(
    url: str,
    destination: Path,
    *,
    timeout_seconds: float = 120.0,
) -> tuple[str, int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    digest = hashlib.sha256()
    size = 0
    content_type = ""
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout_seconds) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
                if not content_type.startswith("video/"):
                    raise Phase11Blocked(
                        "BLOCKED_PHASE11_PROVIDER_RESULT_CONTENT_TYPE",
                        details={"content_type": content_type},
                    )
                with temporary.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        digest.update(chunk)
                        size += len(chunk)
                        handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    if size <= 0:
        raise Phase11Blocked("BLOCKED_PHASE11_PROVIDER_RESULT_EMPTY")
    return f"sha256:{digest.hexdigest()}", size, content_type


def ffprobe_video(path: Path, ffprobe_path: str) -> dict[str, Any]:
    completed = subprocess.run(
        [
            ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate,format_name",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise Phase11Blocked(
            "BLOCKED_PHASE11_FFPROBE_FAILED",
            details={"returncode": completed.returncode, "stderr": completed.stderr[-2000:]},
        )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise Phase11Blocked("BLOCKED_PHASE11_FFPROBE_INVALID_JSON") from exc
    if not isinstance(value, Mapping) or not isinstance(value.get("format"), Mapping):
        raise Phase11Blocked("BLOCKED_PHASE11_FFPROBE_INVALID_JSON")
    return dict(value)


def extract_video_url(result: Mapping[str, Any]) -> str:
    video = result.get("video")
    if isinstance(video, Mapping) and isinstance(video.get("url"), str):
        url = str(video["url"])
    elif isinstance(result.get("video_url"), str):
        url = str(result["video_url"])
    else:
        raise Phase11Blocked("BLOCKED_PHASE11_PROVIDER_RESULT_VIDEO_URL_MISSING")
    if not url.startswith("https://"):
        raise Phase11Blocked("BLOCKED_PHASE11_PROVIDER_RESULT_VIDEO_URL_INVALID")
    return url
