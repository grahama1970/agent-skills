#!/usr/bin/env python3
"""Shared fail-closed helpers for the canonical Persona Dream Phase 11 boundary.

This module performs no provider submission.  It consumes only the qualified
Phase 01-10 revision, local evidence files, and optional Memory HTTP calls used
by the independent validator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlparse

from jsonschema import Draft202012Validator

from activate_revision_qualification import (
    ACTIVATION_RECEIPT_NAME,
    active_pointer_key,
    activation_transaction_id,
    make_file_refs,
    terminal_event,
    validate_existing_activation_receipt,
    validate_local_pointer,
    validate_prepare_verify_chain,
    validate_repair_queue,
)
from prepare_revision_qualification import (
    FORBIDDEN_VECTOR_FIELDS,
    SEMANTIC_REQUIRED_FIELDS,
    SERVER_OWNED_FIELDS,
    GateBlocked,
    MemoryClient,
    http_evidence,
    load_snapshot,
    read_object,
    safe_indexed_file,
    sha256_file,
    sha256_json,
    validate_upsert_result,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "contracts"
DEFAULT_COLLECTION = "project_knowledge"
DEFAULT_MEMORY_URL = "http://127.0.0.1:8601"
DEFAULT_OUTPUT_RELATIVE = Path("phase_11_submit_return") / "canonical"
DEFAULT_CANDIDATE_RELATIVE = Path("phase_11_submit_return") / "preflight" / "phase11_payload_binding.json"
DEFAULT_PROVIDER_SNAPSHOT_RELATIVE = Path("phase_11_submit_return") / "preflight" / "provider_source_snapshot.json"
DEFAULT_TRANSITION_RELATIVE = Path("phase_11_submit_return") / "preflight" / "provider_media_transition_manifest.json"
DEFAULT_APPROVAL_ROOT_RELATIVE = Path("phase_11_submit_return") / "preflight" / "approvals"
DEFAULT_PHASE10_RELATIVE = Path("phase_10_provider_contract") / "final_provider_payload_by_panel.json"
DEFAULT_MEDIA_LOCK_RELATIVE = Path("phase_08_media_lock") / "storyboard_media_lock_manifest.json"

APPROVAL_TYPES = (
    "publication_authorization",
    "visual_media_acceptance",
    "exact_request_acceptance",
    "cost_acceptance",
    "paid_call_authorization",
)
APPROVAL_FILES = {name: f"{name}_receipt.json" for name in APPROVAL_TYPES}
FRAME_IDS = tuple(
    f"sb_{index:03d}.{role}_frame"
    for index in range(1, 5)
    for role in ("start", "end")
)
FRAME_ROLES = {
    "sb_001.start_frame": "global_start_anchor",
    "sb_004.end_frame": "global_end_anchor",
    **{
        artifact_id: "continuity_only"
        for artifact_id in FRAME_IDS
        if artifact_id not in {"sb_001.start_frame", "sb_004.end_frame"}
    },
}
SHA256_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
TIME_RANGE_RE = re.compile(
    r"time\s+range\s+([0-9]+(?:\.[0-9]+)?)s?\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)s?",
    re.IGNORECASE,
)
TIER_RE = re.compile(r"Kling\s+v3\s+(Pro|Standard)\s+I2V", re.IGNORECASE)
SPOKEN_PATTERNS = (
    re.compile(r"dialogue\s+cue\s*:", re.IGNORECASE),
    re.compile(r"\bquietly\s+says\b", re.IGNORECASE),
    re.compile(r"\b(?:he|she|kai|embry)\s+says\b", re.IGNORECASE),
    re.compile(r"[\"“][^\"”]{3,}[\"”]"),
    re.compile(r"'If we paddle now, we're cutting across the lineup\.'", re.IGNORECASE),
)


class Phase11Blocked(RuntimeError):
    def __init__(self, code: str, *, details: Mapping[str, Any] | None = None, exit_code: int = 2) -> None:
        super().__init__(code)
        self.code = code
        self.details = dict(details or {})
        self.exit_code = exit_code


@dataclass(frozen=True)
class ActiveContext:
    run_root: Path
    revision_root: Path
    run_id: str
    revision_id: str
    source_revision_id: str
    source_commit: str
    runtime_release_id: str
    activation_transaction_id: str
    activation_receipt_path: Path
    activation_receipt: dict[str, Any]
    artifact_index_path: Path
    artifact_index: dict[str, Any]
    artifact_index_sha256: str
    revision_manifest_path: Path
    revision_manifest_sha256: str
    local_pointer_path: Path
    local_pointer_sha256: str
    memory_url: str
    collection: str
    mocked: bool
    live: bool


@dataclass(frozen=True)
class ProviderSnapshotResult:
    value: dict[str, Any]
    path: Path
    sha256: str
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class CompilationInputs:
    context: ActiveContext
    phase10_payload_path: Path
    phase10_payload: dict[str, Any]
    candidate_binding_path: Path
    candidate_binding: dict[str, Any]
    media_lock_path: Path
    media_lock: dict[str, Any]
    provider_snapshot: ProviderSnapshotResult
    transition_manifest_path: Path
    transition_manifest: dict[str, Any] | None
    approval_root: Path
    validation_path: Path
    current: datetime


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def pretty_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def serialized_file_sha256(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(pretty_json_bytes(value)).hexdigest()


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pretty_json_bytes(value))


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc)


def now_from_argument(value: str | None) -> datetime:
    return parse_time(value) if value else datetime.now(timezone.utc)


def require(condition: Any, code: str, **details: Any) -> None:
    if not condition:
        raise Phase11Blocked(code, details=details)


def schema_path(name: str) -> Path:
    return CONTRACT_ROOT / name


def validate_schema(value: Mapping[str, Any], name: str) -> list[str]:
    path = schema_path(name)
    if not path.is_file():
        return [f"schema missing: {path}"]
    schema = read_object(path)
    return sorted(error.message for error in Draft202012Validator(schema).iter_errors(value))


def resolve_active_context(run_root: Path, revision_override: str | None = None) -> ActiveContext:
    resolved_run_root = run_root.expanduser().resolve(strict=True)
    pointer_path = resolved_run_root / ".persona-dream" / "state" / "active_revision.json"
    require(pointer_path.is_file(), "BLOCKED_ACTIVE_REVISION_MISSING", path=str(pointer_path))
    pointer = read_object(pointer_path)
    revision_id = str(pointer.get("revisionId") or "")
    require(revision_id, "BLOCKED_ACTIVE_REVISION_MISSING")
    if revision_override is not None and revision_override != revision_id:
        raise Phase11Blocked(
            "BLOCKED_ACTIVE_REVISION_OVERRIDE_MISMATCH",
            details={"active_revision_id": revision_id, "cli_revision_id": revision_override},
        )

    revision_root = resolved_run_root / ".persona-dream" / "revisions" / revision_id
    activation_path = revision_root / ACTIVATION_RECEIPT_NAME
    require(activation_path.is_file(), "BLOCKED_REVISION_ACTIVATION_RECEIPT_MISSING", path=str(activation_path))
    activation = read_object(activation_path)
    require(activation.get("schema") == "persona_dream.revision_activation_receipt.v1", "BLOCKED_REVISION_ACTIVATION_RECEIPT_SCHEMA")
    require(activation.get("status") == "PASS_ACTIVE_CONSISTENT", "BLOCKED_REVISION_ACTIVATION_RECEIPT_STATUS")
    source_commit = str(activation.get("source_commit") or "")
    memory_url = str(activation.get("memory_url") or DEFAULT_MEMORY_URL)
    collection = str(activation.get("collection") or DEFAULT_COLLECTION)
    test_fixture = bool(activation.get("mocked"))
    args = argparse.Namespace(
        run_root=resolved_run_root,
        revision_id=revision_id,
        source_commit=source_commit,
        memory_url=memory_url,
        collection=collection,
        connect_timeout=5.0,
        read_timeout=60.0,
        test_fixture=test_fixture,
    )
    try:
        snapshot = load_snapshot(resolved_run_root, revision_id, source_commit)
        chain = validate_prepare_verify_chain(snapshot, args)
        local_pointer = validate_local_pointer(snapshot)
        queue = validate_repair_queue(snapshot)
        transaction_id = activation_transaction_id(snapshot, chain, local_pointer, queue)
        require(
            activation.get("activation_transaction_id") == transaction_id,
            "BLOCKED_REVISION_ACTIVATION_TRANSACTION_HASH_MISMATCH",
        )
        event_path = queue["event_path"]
        require(event_path.is_file(), "BLOCKED_QUEUE_TERMINAL_EVENT_MISSING", path=str(event_path))
        expected_event = terminal_event(
            snapshot,
            chain,
            local_pointer,
            queue,
            transaction_id=transaction_id,
            active_key=active_pointer_key(snapshot.run_id),
            activated_at=str(activation.get("activated_at") or ""),
            test_fixture=test_fixture,
        )
        observed_event = read_object(event_path)
        require(
            canonical_json_bytes(observed_event) == canonical_json_bytes(expected_event),
            "BLOCKED_QUEUE_TERMINAL_EVENT_MISMATCH",
        )
        file_refs = make_file_refs(snapshot, chain, local_pointer, queue, event_path)
        memory = activation.get("memory")
        require(isinstance(memory, Mapping), "BLOCKED_MEMORY_ACTIVE_REVISION_UNPROVEN")
        semantic_pointer = {
            field: memory.get(field)
            for field in (
                "document_contract_sha256",
                "qdrant_collection",
                "qdrant_point_id",
                "embedding_model",
                "embedding_version",
                "text_hash",
                "semantic_sync_state",
            )
        }
        validate_existing_activation_receipt(
            activation,
            snapshot=snapshot,
            args=args,
            transaction_id=transaction_id,
            active_key=active_pointer_key(snapshot.run_id),
            file_refs=file_refs,
            semantic_pointer=semantic_pointer,
            queue=queue,
        )
    except GateBlocked as exc:
        raise Phase11Blocked(exc.code, details=exc.details, exit_code=exc.exit_code) from exc

    artifact_index = read_object(snapshot.index_path)
    return ActiveContext(
        run_root=resolved_run_root,
        revision_root=snapshot.revision_root,
        run_id=snapshot.run_id,
        revision_id=snapshot.revision_id,
        source_revision_id=snapshot.source_revision_id,
        source_commit=snapshot.source_commit,
        runtime_release_id=str(chain["runtime_release_id"]),
        activation_transaction_id=transaction_id,
        activation_receipt_path=activation_path,
        activation_receipt=activation,
        artifact_index_path=snapshot.index_path,
        artifact_index=artifact_index,
        artifact_index_sha256=snapshot.index_sha256,
        revision_manifest_path=snapshot.manifest_path,
        revision_manifest_sha256=snapshot.manifest_sha256,
        local_pointer_path=local_pointer["path"],
        local_pointer_sha256=local_pointer["sha256"],
        memory_url=memory_url,
        collection=collection,
        mocked=test_fixture,
        live=bool(activation.get("live")),
    )


def resolve_path(base: Path, value: Path | None, default_relative: Path) -> Path:
    if value is not None:
        return value.expanduser().resolve()
    return (base / default_relative).resolve()


def provider_mode(endpoint: str) -> str:
    lowered = endpoint.lower()
    if "/standard/" in lowered:
        return "standard"
    if "/pro/" in lowered:
        return "pro"
    return "unknown"


def load_provider_snapshot(path: Path, current: datetime) -> ProviderSnapshotResult:
    blockers: list[str] = []
    if not path.is_file():
        placeholder = {
            "schema": "persona_dream.phase11_provider_source_snapshot.v1",
            "provider_id": "kling",
            "endpoint": "",
            "mode": "unknown",
            "actual_provider_call_attempts": 0,
        }
        return ProviderSnapshotResult(placeholder, path, "sha256:" + "0" * 64, ("BLOCKED_PROVIDER_SOURCE_SNAPSHOT_MISSING",))

    value = read_object(path)
    errors = validate_schema(value, "phase11_provider_source_snapshot.v1.schema.json")
    blockers.extend(f"BLOCKED_PROVIDER_SOURCE_SNAPSHOT_SCHEMA:{error}" for error in errors)
    snapshot_sha = sha256_file(path)
    if value.get("actual_provider_call_attempts") != 0:
        blockers.append("BLOCKED_PROVIDER_CALL_ATTEMPT_NONZERO")
    endpoint = str(value.get("endpoint") or "")
    mode = str(value.get("mode") or "").lower()
    if provider_mode(endpoint) != mode:
        blockers.append("BLOCKED_PROVIDER_STANDARD_PRO_MODE_MISMATCH")
    try:
        retrieved = parse_time(str(value.get("retrieved_at") or ""))
        ttl_seconds = int(value.get("ttl_seconds") or 0)
        if ttl_seconds <= 0 or current.timestamp() > retrieved.timestamp() + ttl_seconds:
            blockers.append("BLOCKED_PROVIDER_SOURCE_SNAPSHOT_TTL_EXPIRED")
    except (TypeError, ValueError):
        blockers.append("BLOCKED_PROVIDER_SOURCE_SNAPSHOT_TIMESTAMP_INVALID")
    for source_name in ("schema_source", "pricing_source"):
        source = value.get(source_name)
        if not isinstance(source, Mapping):
            blockers.append(f"BLOCKED_PROVIDER_{source_name.upper()}_MISSING")
            continue
        if not 200 <= int(source.get("http_status") or 0) < 300:
            blockers.append(f"BLOCKED_PROVIDER_{source_name.upper()}_HTTP_STATUS")
        final_url = str(source.get("final_url") or "")
        if urlparse(final_url).scheme != "https":
            blockers.append(f"BLOCKED_PROVIDER_{source_name.upper()}_FINAL_URL")
        expected_remote_hash = str(source.get("remote_content_sha256") or "")
        if not SHA256_RE.fullmatch(expected_remote_hash):
            blockers.append(f"BLOCKED_PROVIDER_{source_name.upper()}_REMOTE_HASH")
        body_relative = str(source.get("body_relative_path") or "")
        body_path = path.parent / body_relative
        try:
            resolved_parent = path.parent.resolve(strict=True)
            resolved_body = body_path.resolve(strict=True)
            resolved_body.relative_to(resolved_parent)
            if sha256_file(resolved_body) != expected_remote_hash:
                blockers.append(f"BLOCKED_PROVIDER_{source_name.upper()}_BODY_HASH")
        except (OSError, ValueError):
            blockers.append(f"BLOCKED_PROVIDER_{source_name.upper()}_BODY_EVIDENCE")
    schema_source = value.get("schema_source")
    if isinstance(schema_source, Mapping):
        input_schema = schema_source.get("input_schema")
        if not isinstance(input_schema, Mapping):
            blockers.append("BLOCKED_PROVIDER_INPUT_SCHEMA_MISSING")
        else:
            for field in ("start_image_url", "end_image_url", "multi_prompt", "elements", "generate_audio", "duration"):
                if field not in input_schema:
                    blockers.append(f"BLOCKED_PROVIDER_INPUT_SCHEMA_FIELD:{field}")
            start_contract = input_schema.get("start_image_url")
            if not isinstance(start_contract, Mapping) or start_contract.get("required") is not True:
                blockers.append("BLOCKED_PROVIDER_START_IMAGE_SCHEMA")
            duration_contract = input_schema.get("duration")
            allowed = duration_contract.get("enum") if isinstance(duration_contract, Mapping) else None
            if isinstance(allowed, list) and 10 not in allowed and "10" not in allowed:
                blockers.append("BLOCKED_PROVIDER_DURATION_NOT_SUPPORTED")
            normalized_expected = str(schema_source.get("normalized_schema_sha256") or "")
            if normalized_expected != canonical_sha256(input_schema):
                blockers.append("BLOCKED_PROVIDER_NORMALIZED_SCHEMA_HASH")
    pricing = value.get("pricing_source")
    if isinstance(pricing, Mapping):
        try:
            duration = int(pricing.get("duration_seconds") or 0)
            rate = float(pricing.get("usd_per_second_audio_off") or 0)
            maximum = float(pricing.get("maximum_expected_cost_usd") or 0)
            if duration != 10 or rate <= 0 or abs(maximum - rate * duration) > 1e-9:
                blockers.append("BLOCKED_PROVIDER_PRICING_CONTRACT")
        except (TypeError, ValueError):
            blockers.append("BLOCKED_PROVIDER_PRICING_CONTRACT")
    return ProviderSnapshotResult(value, path, snapshot_sha, tuple(sorted(set(blockers))))


def load_inputs(
    run_root: Path,
    *,
    revision_override: str | None,
    phase10_payload: Path | None,
    candidate_binding: Path | None,
    media_lock: Path | None,
    provider_snapshot: Path | None,
    transition_manifest: Path | None,
    approval_root: Path | None,
    current: datetime,
) -> CompilationInputs:
    context = resolve_active_context(run_root, revision_override)
    phase10_path = resolve_path(context.revision_root, phase10_payload, DEFAULT_PHASE10_RELATIVE)
    candidate_path = resolve_path(context.revision_root, candidate_binding, DEFAULT_CANDIDATE_RELATIVE)
    media_lock_path = resolve_path(context.revision_root, media_lock, DEFAULT_MEDIA_LOCK_RELATIVE)
    provider_path = resolve_path(context.revision_root, provider_snapshot, DEFAULT_PROVIDER_SNAPSHOT_RELATIVE)
    transition_path = resolve_path(context.revision_root, transition_manifest, DEFAULT_TRANSITION_RELATIVE)
    approvals = resolve_path(context.revision_root, approval_root, DEFAULT_APPROVAL_ROOT_RELATIVE)
    validation_path = context.run_root / "validation.json"

    phase10_value = read_object(phase10_path) if phase10_path.is_file() else {}
    candidate_value = read_object(candidate_path) if candidate_path.is_file() else {}
    media_lock_value = read_object(media_lock_path) if media_lock_path.is_file() else {}
    transition_value = read_object(transition_path) if transition_path.is_file() else None
    return CompilationInputs(
        context=context,
        phase10_payload_path=phase10_path,
        phase10_payload=phase10_value,
        candidate_binding_path=candidate_path,
        candidate_binding=candidate_value,
        media_lock_path=media_lock_path,
        media_lock=media_lock_value,
        provider_snapshot=load_provider_snapshot(provider_path, current),
        transition_manifest_path=transition_path,
        transition_manifest=transition_value,
        approval_root=approvals,
        validation_path=validation_path,
        current=current,
    )


def index_artifacts(context: ActiveContext) -> dict[str, dict[str, Any]]:
    raw = context.artifact_index.get("artifacts")
    require(isinstance(raw, dict), "BLOCKED_REVISION_ARTIFACT_INDEX_INVALID")
    return {str(key): dict(value) for key, value in raw.items() if isinstance(value, dict)}


def artifact_for_url(context: ActiveContext, url: str) -> tuple[str, dict[str, Any]]:
    parsed = urlparse(url)
    require(parsed.scheme == "https", "BLOCKED_PROVIDER_MEDIA_URL_INVALID", url=url)
    url_path = unquote(parsed.path).lstrip("/")
    matches: list[tuple[str, dict[str, Any]]] = []
    for artifact_id, entry in index_artifacts(context).items():
        relative_path = str(entry.get("relative_path") or "").lstrip("/")
        if relative_path and (url_path == relative_path or url_path.endswith("/" + relative_path)):
            matches.append((artifact_id, entry))
    require(len(matches) == 1, "BLOCKED_PROVIDER_MEDIA_URL_ARTIFACT_MAPPING", url=url, matches=[item[0] for item in matches])
    artifact_id, entry = matches[0]
    local = safe_indexed_file(context.revision_root, str(entry["relative_path"]))
    require(sha256_file(local) == entry.get("sha256"), "BLOCKED_PROVIDER_MEDIA_LOCAL_HASH_MISMATCH", artifact_id=artifact_id)
    return artifact_id, entry


def transition_entries(value: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    entries = value.get("entries")
    if not isinstance(entries, list):
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        if isinstance(entry, Mapping) and isinstance(entry.get("artifact_id"), str):
            result[str(entry["artifact_id"])] = entry
    return result


def validate_transition_evidence(
    inputs: CompilationInputs,
    *,
    artifact_id: str,
    url: str,
    expected_sha256: str,
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    entry = transition_entries(inputs.transition_manifest).get(artifact_id)
    if entry is None:
        return {"manifest_path": str(inputs.transition_manifest_path), "entry_found": False}, [f"BLOCKED_PUBLIC_MEDIA_TRANSITION_EVIDENCE:{artifact_id}"]
    if entry.get("url") != url or entry.get("sha256") != expected_sha256:
        blockers.append(f"BLOCKED_PUBLIC_MEDIA_TRANSITION_BINDING:{artifact_id}")
    refs: dict[str, Any] = {}
    for name in ("publication_authorization", "publication_receipt", "public_probe", "teardown_policy"):
        ref = entry.get(name)
        if not isinstance(ref, Mapping):
            blockers.append(f"BLOCKED_PUBLIC_MEDIA_{name.upper()}_MISSING:{artifact_id}")
            continue
        relative_path = str(ref.get("relative_path") or "")
        expected_hash = str(ref.get("sha256") or "")
        try:
            path = (inputs.context.run_root / relative_path).resolve(strict=True)
            path.relative_to(inputs.context.run_root)
            observed_hash = sha256_file(path)
            if observed_hash != expected_hash:
                blockers.append(f"BLOCKED_PUBLIC_MEDIA_{name.upper()}_HASH:{artifact_id}")
                continue
            receipt = read_object(path)
        except (OSError, ValueError, json.JSONDecodeError):
            blockers.append(f"BLOCKED_PUBLIC_MEDIA_{name.upper()}_INVALID:{artifact_id}")
            continue
        refs[name] = {"relative_path": relative_path, "sha256": observed_hash, "status": receipt.get("status")}
        if name == "publication_authorization":
            if receipt.get("status") != "APPROVED" or receipt.get("approval_type") != "publication_authorization":
                blockers.append(f"BLOCKED_PUBLIC_MEDIA_PUBLICATION_AUTHORIZATION:{artifact_id}")
        elif name == "publication_receipt":
            if receipt.get("status") not in {"PUBLISHED", "PASS_PROVIDER_MEDIA_PUBLISHED"}:
                blockers.append(f"BLOCKED_PUBLIC_MEDIA_PUBLICATION_RECEIPT:{artifact_id}")
        elif name == "public_probe":
            probe_sha = receipt.get("downloaded_sha256") or receipt.get("observed_sha256")
            final_url = receipt.get("final_url") or receipt.get("url")
            if receipt.get("status") not in {"PASS", "PASS_PROVIDER_MEDIA_PUBLIC_FETCH"} or int(receipt.get("http_status") or 0) != 200 or probe_sha != expected_sha256 or final_url != url:
                blockers.append(f"BLOCKED_PUBLIC_MEDIA_PROBE:{artifact_id}")
        elif name == "teardown_policy":
            if receipt.get("status") not in {"NOT_REQUIRED_PERSISTENT_COMMIT_PINNED", "PASS_PROVIDER_MEDIA_TEARDOWN"}:
                blockers.append(f"BLOCKED_PUBLIC_MEDIA_TEARDOWN_POLICY:{artifact_id}")
    return {"manifest_path": str(inputs.transition_manifest_path), "entry_found": True, **refs}, blockers


def build_media_binding_manifest(inputs: CompilationInputs, request_body: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    locked = inputs.media_lock.get("assets")
    locked_assets = [dict(item) for item in locked] if isinstance(locked, list) and all(isinstance(item, dict) for item in locked) else []
    by_id = {str(item.get("asset_id") or ""): item for item in locked_assets}
    if len(locked_assets) != 8:
        blockers.append(f"BLOCKED_LOCKED_ASSET_CARDINALITY:{len(locked_assets)}:expected:8")
    if set(by_id) != set(FRAME_IDS):
        blockers.append("BLOCKED_LOCKED_STORYBOARD_FRAME_SET")

    start_url = str(request_body.get("start_image_url") or "")
    end_url = str(request_body.get("end_image_url") or "")
    frame_records: list[dict[str, Any]] = []
    for artifact_id in FRAME_IDS:
        source = by_id.get(artifact_id, {})
        role = FRAME_ROLES[artifact_id]
        pointer = "/input/start_image_url" if role == "global_start_anchor" else "/input/end_image_url" if role == "global_end_anchor" else None
        url = start_url if role == "global_start_anchor" else end_url if role == "global_end_anchor" else None
        record = {
            "artifact_id": artifact_id,
            "role": role,
            "json_pointer": pointer,
            "sha256": source.get("sha256"),
            "revision_relative_path": source.get("path"),
            "public_url": url,
            "transition_evidence": None,
        }
        if artifact_id not in by_id or not SHA256_RE.fullmatch(str(source.get("sha256") or "")):
            blockers.append(f"BLOCKED_MEDIA_ID_OR_HASH_MISSING:{artifact_id}")
        if pointer:
            try:
                mapped_id, entry = artifact_for_url(inputs.context, str(url or ""))
                if mapped_id != artifact_id or entry.get("sha256") != source.get("sha256"):
                    blockers.append(f"BLOCKED_PROVIDER_ANCHOR_MAPPING:{artifact_id}")
                evidence, evidence_blockers = validate_transition_evidence(
                    inputs,
                    artifact_id=artifact_id,
                    url=str(url or ""),
                    expected_sha256=str(source.get("sha256") or ""),
                )
                record["transition_evidence"] = evidence
                blockers.extend(evidence_blockers)
            except (Phase11Blocked, GateBlocked) as exc:
                blockers.append(getattr(exc, "code", "BLOCKED_PROVIDER_ANCHOR_MAPPING"))
        frame_records.append(record)

    elements = request_body.get("elements")
    element_values = [dict(item) for item in elements] if isinstance(elements, list) and all(isinstance(item, dict) for item in elements) else []
    if len(element_values) != 2:
        blockers.append(f"BLOCKED_CHARACTER_ELEMENT_PACK_COUNT:{len(element_values)}:expected:2")
    element_packs: list[dict[str, Any]] = []
    for index, element in enumerate(element_values[:2]):
        identity = "embry" if index == 0 else "kai"
        images: list[tuple[str, str, str]] = []
        frontal = str(element.get("frontal_image_url") or "")
        if frontal:
            images.append(("frontal", f"/input/elements/{index}/frontal_image_url", frontal))
        references = element.get("reference_image_urls")
        if isinstance(references, list):
            for ref_index, value in enumerate(references):
                images.append(("reference", f"/input/elements/{index}/reference_image_urls/{ref_index}", str(value)))
        if not 2 <= len(images) <= 4:
            blockers.append(f"BLOCKED_CHARACTER_ELEMENT_PACK_IMAGE_COUNT:{identity}:{len(images)}")
        image_records: list[dict[str, Any]] = []
        for image_role, pointer, url in images:
            try:
                artifact_id, entry = artifact_for_url(inputs.context, url)
                evidence, evidence_blockers = validate_transition_evidence(
                    inputs,
                    artifact_id=artifact_id,
                    url=url,
                    expected_sha256=str(entry.get("sha256") or ""),
                )
                blockers.extend(evidence_blockers)
                image_records.append({
                    "role": image_role,
                    "json_pointer": pointer,
                    "artifact_id": artifact_id,
                    "sha256": entry.get("sha256"),
                    "revision_relative_path": entry.get("relative_path"),
                    "public_url": url,
                    "transition_evidence": evidence,
                })
            except (Phase11Blocked, GateBlocked) as exc:
                blockers.append(getattr(exc, "code", f"BLOCKED_CHARACTER_ELEMENT_PACK_MAPPING:{identity}"))
        element_packs.append({
            "identity": identity,
            "prompt_token": f"@Element{index + 1}",
            "element_index": index,
            "images": image_records,
        })

    role_counts = {
        "global_start_anchor": sum(item["role"] == "global_start_anchor" for item in frame_records),
        "global_end_anchor": sum(item["role"] == "global_end_anchor" for item in frame_records),
        "continuity_only": sum(item["role"] == "continuity_only" for item in frame_records),
        "element_packs": len(element_packs),
    }
    if role_counts != {"global_start_anchor": 1, "global_end_anchor": 1, "continuity_only": 6, "element_packs": 2}:
        blockers.append("BLOCKED_MEDIA_ROLE_COUNTS")

    source_contract = {
        "run_id": inputs.context.run_id,
        "revision_id": inputs.context.revision_id,
        "frames": [
            {key: item.get(key) for key in ("artifact_id", "role", "json_pointer", "sha256", "public_url")}
            for item in frame_records
        ],
        "element_packs": [
            {
                "identity": item["identity"],
                "prompt_token": item["prompt_token"],
                "images": [
                    {key: image.get(key) for key in ("role", "json_pointer", "artifact_id", "sha256", "public_url")}
                    for image in item["images"]
                ],
            }
            for item in element_packs
        ],
    }
    return {
        "schema": "persona_dream.phase11_media_binding_manifest.v2",
        "status": "PASS_PHASE11_MEDIA_BINDING_TECHNICAL" if not blockers else "BLOCKED_PROVIDER_GATE",
        "run_id": inputs.context.run_id,
        "revision_id": inputs.context.revision_id,
        "activation_transaction_id": inputs.context.activation_transaction_id,
        "source_files": {
            "media_lock": {"path": str(inputs.media_lock_path), "sha256": sha256_file(inputs.media_lock_path) if inputs.media_lock_path.is_file() else None},
            "candidate_binding": {"path": str(inputs.candidate_binding_path), "sha256": sha256_file(inputs.candidate_binding_path) if inputs.candidate_binding_path.is_file() else None},
            "artifact_index": {"path": str(inputs.context.artifact_index_path), "sha256": inputs.context.artifact_index_sha256},
            "transition_manifest": {"path": str(inputs.transition_manifest_path), "sha256": sha256_file(inputs.transition_manifest_path) if inputs.transition_manifest_path.is_file() else None},
        },
        "media_input_contract_sha256": canonical_sha256(source_contract),
        "role_counts": role_counts,
        "storyboard_frames": frame_records,
        "element_packs": element_packs,
        "publication_policy": {
            "authorization_required": True,
            "publication_receipt_required": True,
            "public_probe_required": True,
            "teardown_policy_required": True,
            "existing_url_without_transition_evidence_blocks": True,
        },
        "blockers": sorted(set(blockers)),
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "submitted": False,
    }


def normalize_prompt(prompt: str, *, panel_id: str, duration: int, start: int, end: int, mode: str) -> tuple[str, list[str]]:
    changes: list[str] = []
    expected_label = "Standard" if mode == "standard" else "Pro" if mode == "pro" else mode.title()
    replaced = TIER_RE.sub(f"Kling v3 {expected_label} I2V", prompt)
    if replaced != prompt:
        changes.append("provider_tier_normalized")
    prompt = TIME_RANGE_RE.sub(f"time range {start}s-{end}s", replaced)
    if prompt != replaced:
        changes.append("time_range_normalized")
    if panel_id == "sb_003":
        before = prompt
        prompt = re.sub(
            r"then gives one restrained cue:\s*['\"“].*?['\"”]\s*Embry remains",
            "then gives one restrained nonverbal hand signal to wait. Embry remains",
            prompt,
            flags=re.IGNORECASE,
        )
        prompt = re.sub(
            r"Dialogue cue:.*?(?=Avoid identity drift)",
            "No spoken dialogue. Kai communicates only through gaze, posture, and one restrained hand signal. No lip movement, captions, dialogue text, or speech bubbles. ",
            prompt,
            flags=re.IGNORECASE | re.DOTALL,
        )
        prompt = re.sub(r"['\"“]If we paddle now, we're cutting across the lineup\.[\"”']", "", prompt, flags=re.IGNORECASE)
        prompt = re.sub(r"\s{2,}", " ", prompt).strip()
        if prompt != before:
            changes.append("sb003_dialogue_removed")
    return prompt, changes


def source_multi_prompt(inputs: CompilationInputs) -> list[dict[str, Any]]:
    candidate_input = inputs.candidate_binding.get("input")
    if isinstance(candidate_input, Mapping) and isinstance(candidate_input.get("multi_prompt"), list):
        return [dict(item) for item in candidate_input["multi_prompt"] if isinstance(item, Mapping)]
    preview = inputs.phase10_payload.get("assembled_request_preview")
    if isinstance(preview, Mapping):
        request_input = preview.get("input")
        if isinstance(request_input, Mapping) and isinstance(request_input.get("multi_prompt"), list):
            return [dict(item) for item in request_input["multi_prompt"] if isinstance(item, Mapping)]
    return []


def compile_request_body(inputs: CompilationInputs) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    blockers: list[str] = list(inputs.provider_snapshot.blockers)
    snapshot = inputs.provider_snapshot.value
    endpoint = str(snapshot.get("endpoint") or inputs.candidate_binding.get("model") or "")
    mode = str(snapshot.get("mode") or inputs.candidate_binding.get("mode") or provider_mode(endpoint)).lower()
    candidate_model = str(inputs.candidate_binding.get("model") or "")
    phase10_model = str((inputs.phase10_payload.get("assembled_request_preview") or {}).get("model") or inputs.phase10_payload.get("endpoint") or "") if isinstance(inputs.phase10_payload, Mapping) else ""
    if candidate_model and endpoint and candidate_model != endpoint:
        blockers.append("BLOCKED_PROVIDER_ENDPOINT_CANDIDATE_MISMATCH")
    if phase10_model and endpoint and phase10_model != endpoint:
        blockers.append("BLOCKED_PROVIDER_ENDPOINT_CHANGED_FROM_PHASE10")
    if provider_mode(endpoint) != mode:
        blockers.append("BLOCKED_PROVIDER_STANDARD_PRO_MODE_MISMATCH")

    raw_prompts = source_multi_prompt(inputs)
    if len(raw_prompts) != 4:
        blockers.append(f"BLOCKED_PROVIDER_SHOT_COUNT:{len(raw_prompts)}:expected:4")
    expected_durations = [2, 3, 2, 3]
    cumulative = 0
    compiled_prompts: list[dict[str, Any]] = []
    transformations: list[dict[str, Any]] = []
    for index, expected_duration in enumerate(expected_durations):
        panel_id = f"sb_{index + 1:03d}"
        raw = raw_prompts[index] if index < len(raw_prompts) else {}
        try:
            observed_duration = int(raw.get("duration") or 0)
        except (TypeError, ValueError):
            observed_duration = 0
        if observed_duration != expected_duration:
            blockers.append(f"BLOCKED_PROVIDER_SHOT_DURATION:{panel_id}:{observed_duration}:expected:{expected_duration}")
        normalized, changes = normalize_prompt(
            str(raw.get("prompt") or ""),
            panel_id=panel_id,
            duration=expected_duration,
            start=cumulative,
            end=cumulative + expected_duration,
            mode=mode,
        )
        compiled_prompts.append({"duration": str(expected_duration), "prompt": normalized})
        transformations.append({"panel_id": panel_id, "changes": changes})
        cumulative += expected_duration

    candidate_input = inputs.candidate_binding.get("input")
    candidate_input = dict(candidate_input) if isinstance(candidate_input, Mapping) else {}
    request_body: dict[str, Any] = {
        "multi_prompt": compiled_prompts,
        "start_image_url": candidate_input.get("start_image_url"),
        "duration": "10",
        "generate_audio": False,
        "end_image_url": candidate_input.get("end_image_url"),
        "elements": candidate_input.get("elements") if isinstance(candidate_input.get("elements"), list) else [],
        "shot_type": candidate_input.get("shot_type") or "customize",
        "negative_prompt": str(candidate_input.get("negative_prompt") or "").strip(),
        "cfg_scale": candidate_input.get("cfg_scale", 0.5),
    }
    speech_negative = "no audible speech, no lip-sync, no mouth articulating words, no subtitles, no captions, no dialogue text, no speech bubbles"
    if speech_negative.lower() not in request_body["negative_prompt"].lower():
        request_body["negative_prompt"] = (request_body["negative_prompt"].rstrip("; ") + "; " + speech_negative).strip("; ")

    blockers.extend(validate_request_body(request_body, endpoint=endpoint, mode=mode))
    return request_body, sorted(set(blockers)), transformations


def validate_request_body(body: Mapping[str, Any], *, endpoint: str, mode: str) -> list[str]:
    blockers: list[str] = []
    if "prompt" in body:
        blockers.append("BLOCKED_PROVIDER_PROMPT_AND_MULTI_PROMPT_CONFLICT")
    prompts = body.get("multi_prompt")
    if not isinstance(prompts, list) or len(prompts) != 4:
        blockers.append("BLOCKED_PROVIDER_MULTI_PROMPT_CARDINALITY")
        return blockers
    if body.get("generate_audio") is not False:
        blockers.append("BLOCKED_PROVIDER_AUDIO_STRATEGY")
    if not isinstance(body.get("start_image_url"), str) or not body.get("start_image_url"):
        blockers.append("BLOCKED_PROVIDER_START_IMAGE_URL_MISSING")
    if not isinstance(body.get("end_image_url"), str) or not body.get("end_image_url"):
        blockers.append("BLOCKED_PROVIDER_END_IMAGE_URL_MISSING")
    if body.get("duration") != "10":
        blockers.append("BLOCKED_PROVIDER_DURATION")
    if not isinstance(body.get("elements"), list) or len(body.get("elements")) != 2:
        blockers.append("BLOCKED_CHARACTER_ELEMENT_PACK_COUNT")
    if provider_mode(endpoint) != mode:
        blockers.append("BLOCKED_PROVIDER_STANDARD_PRO_MODE_MISMATCH")

    elapsed = 0
    for index, item in enumerate(prompts):
        panel_id = f"sb_{index + 1:03d}"
        if not isinstance(item, Mapping):
            blockers.append(f"BLOCKED_PROVIDER_SHOT_INVALID:{panel_id}")
            continue
        try:
            duration = int(item.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0
        prompt = str(item.get("prompt") or "")
        match = TIME_RANGE_RE.search(prompt)
        if match is None:
            blockers.append(f"BLOCKED_PROVIDER_TIME_RANGE_MISSING:{panel_id}")
        else:
            start = float(match.group(1))
            end = float(match.group(2))
            if abs(start - elapsed) > 1e-9 or abs(end - (elapsed + duration)) > 1e-9:
                blockers.append(f"BLOCKED_PROVIDER_TIME_RANGE_CONTRADICTION:{panel_id}")
        tiers = {match.group(1).lower() for match in TIER_RE.finditer(prompt)}
        if tiers and tiers != {mode}:
            blockers.append(f"BLOCKED_PROVIDER_STANDARD_PRO_NAMING_CONFLICT:{panel_id}")
        if panel_id == "sb_003" and any(pattern.search(prompt) for pattern in SPOKEN_PATTERNS):
            blockers.append("BLOCKED_PROVIDER_AUDIO_OFF_SPOKEN_DIALOGUE:sb_003")
        elapsed += duration
    if elapsed != 10:
        blockers.append(f"BLOCKED_PROVIDER_TOTAL_DURATION:{elapsed}:expected:10")

    def contains_null(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, Mapping):
            return any(contains_null(item) for item in value.values())
        if isinstance(value, list):
            return any(contains_null(item) for item in value)
        return False

    if contains_null(body):
        blockers.append("BLOCKED_PROVIDER_REQUEST_NULL_FIELD")
    return blockers


def upstream_validation_blockers(path: Path) -> list[str]:
    if not path.is_file():
        return ["BLOCKED_UPSTREAM_VALIDATION_MISSING"]
    value = read_object(path)
    try:
        passed = int(value.get("passed_step_count") or 0)
        total = int(value.get("step_count") or 0)
    except (TypeError, ValueError):
        return ["BLOCKED_UPSTREAM_VALIDATION_INVALID"]
    blockers: list[str] = []
    if total <= 0 or passed != total:
        blockers.append(f"BLOCKED_UPSTREAM_VALIDATION_INCOMPLETE:{passed}/{total}")
    if passed != total and value.get("first_blocker") is None:
        blockers.append("BLOCKED_UPSTREAM_VALIDATION_FALSE_GREEN_FIRST_BLOCKER_NULL")
    return blockers


def approval_bindings(
    inputs: CompilationInputs,
    *,
    media_manifest_sha256: str,
    media_input_contract_sha256: str,
    provider_snapshot_sha256: str,
    request_body_sha256: str,
) -> dict[str, Any]:
    pricing = inputs.provider_snapshot.value.get("pricing_source")
    pricing_sha = canonical_sha256(pricing if isinstance(pricing, Mapping) else {})
    return {
        "run_id": inputs.context.run_id,
        "revision_id": inputs.context.revision_id,
        "activation_transaction_id": inputs.context.activation_transaction_id,
        "provider_id": str(inputs.provider_snapshot.value.get("provider_id") or "kling"),
        "endpoint": str(inputs.provider_snapshot.value.get("endpoint") or ""),
        "request_body_sha256": request_body_sha256,
        "media_binding_manifest_sha256": media_manifest_sha256,
        "media_input_contract_sha256": media_input_contract_sha256,
        "provider_source_snapshot_sha256": provider_snapshot_sha256,
        "pricing_snapshot_sha256": pricing_sha,
        "actual_provider_call_attempts": 0,
    }


def inspect_approvals(root: Path, bindings: Mapping[str, Any], current: datetime) -> tuple[dict[str, Any], list[str], list[str]]:
    statuses: dict[str, Any] = {}
    missing: list[str] = []
    blockers: list[str] = []
    for approval_type in APPROVAL_TYPES:
        path = root / APPROVAL_FILES[approval_type]
        if not path.is_file():
            statuses[approval_type] = {"path": str(path), "state": "MISSING", "sha256": None}
            missing.append(approval_type)
            continue
        try:
            receipt = read_object(path)
        except (OSError, json.JSONDecodeError, ValueError):
            statuses[approval_type] = {"path": str(path), "state": "INVALID", "sha256": None}
            blockers.append(f"BLOCKED_APPROVAL_RECEIPT_INVALID:{approval_type}")
            continue
        errors = validate_schema(receipt, "phase11_approval_receipt.v1.schema.json")
        if errors:
            blockers.append(f"BLOCKED_APPROVAL_RECEIPT_SCHEMA:{approval_type}")
        if receipt.get("approval_type") != approval_type or receipt.get("status") != "APPROVED":
            blockers.append(f"BLOCKED_APPROVAL_RECEIPT_STATUS:{approval_type}")
        expected_bindings = dict(bindings)
        if approval_type == "publication_authorization":
            expected_bindings.pop("media_binding_manifest_sha256", None)
            expected_kind = "media_input_contract"
            expected_binding_sha = str(bindings["media_input_contract_sha256"])
        else:
            expected_kind = "phase11_request_bundle"
            expected_binding_sha = canonical_sha256(bindings)
        for field, expected in expected_bindings.items():
            if receipt.get(field) != expected:
                blockers.append(f"BLOCKED_APPROVAL_RECEIPT_BINDING:{approval_type}:{field}")
        if receipt.get("approval_binding_kind") != expected_kind or receipt.get("approval_binding_sha256") != expected_binding_sha:
            blockers.append(f"BLOCKED_APPROVAL_RECEIPT_BINDING:{approval_type}:approval_binding")
        try:
            if parse_time(str(receipt.get("expires_at") or "")) <= current:
                blockers.append(f"BLOCKED_APPROVAL_RECEIPT_EXPIRED:{approval_type}")
        except ValueError:
            blockers.append(f"BLOCKED_APPROVAL_RECEIPT_EXPIRY:{approval_type}")
        statuses[approval_type] = {
            "path": str(path),
            "state": "APPROVED" if not any(code.startswith(f"BLOCKED_APPROVAL_RECEIPT") and f":{approval_type}" in code for code in blockers) else "INVALID",
            "sha256": sha256_file(path),
        }
    return statuses, sorted(set(missing)), sorted(set(blockers))


def compile_bundle(inputs: CompilationInputs) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    request_body, request_blockers, transformations = compile_request_body(inputs)
    media_manifest = build_media_binding_manifest(inputs, request_body)
    request_body_sha = canonical_sha256(request_body)
    media_manifest_sha = serialized_file_sha256(media_manifest)
    bindings = approval_bindings(
        inputs,
        media_manifest_sha256=media_manifest_sha,
        media_input_contract_sha256=str(media_manifest["media_input_contract_sha256"]),
        provider_snapshot_sha256=inputs.provider_snapshot.sha256,
        request_body_sha256=request_body_sha,
    )
    approval_statuses, missing_approvals, approval_blockers = inspect_approvals(inputs.approval_root, bindings, inputs.current)
    technical_blockers = sorted(set(
        request_blockers
        + list(media_manifest.get("blockers") or [])
        + upstream_validation_blockers(inputs.validation_path)
        + approval_blockers
    ))
    if technical_blockers:
        gate_status = "BLOCKED_PROVIDER_GATE"
    elif missing_approvals:
        gate_status = "BLOCKED_AWAITING_HUMAN_APPROVAL"
    else:
        technical_blockers.append("BLOCKED_PROVIDER_SUBMISSION_ADAPTER_OUT_OF_SCOPE")
        gate_status = "BLOCKED_PROVIDER_GATE"

    approval_requirements = {
        "schema": "persona_dream.phase11_approval_requirements.v1",
        "status": "COMPLETE" if not missing_approvals and not approval_blockers else "INCOMPLETE",
        "bindings": bindings,
        "required_approval_types": list(APPROVAL_TYPES),
        "receipts": approval_statuses,
        "missing_approval_types": missing_approvals,
        "blockers": approval_blockers,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "submitted": False,
    }
    endpoint = str(inputs.provider_snapshot.value.get("endpoint") or inputs.candidate_binding.get("model") or "")
    mode = str(inputs.provider_snapshot.value.get("mode") or inputs.candidate_binding.get("mode") or provider_mode(endpoint)).lower()
    pricing = inputs.provider_snapshot.value.get("pricing_source")
    live_request = {
        "schema": "persona_dream.phase11_live_request.v1",
        "status": gate_status,
        "run_id": inputs.context.run_id,
        "revision_id": inputs.context.revision_id,
        "source_revision_id": inputs.context.source_revision_id,
        "source_commit": inputs.context.source_commit,
        "runtime_release_id": inputs.context.runtime_release_id,
        "activation_transaction_id": inputs.context.activation_transaction_id,
        "activation_receipt_sha256": sha256_file(inputs.context.activation_receipt_path),
        "provider_id": str(inputs.provider_snapshot.value.get("provider_id") or "kling"),
        "endpoint": endpoint,
        "mode": mode,
        "provider_request_body": request_body,
        "request_body_canonicalization": {
            "encoding": "UTF-8",
            "json": "RFC8259",
            "sort_keys": True,
            "separators": [",", ":"],
            "ensure_ascii": False,
        },
        "request_body_sha256": request_body_sha,
        "source_files": {
            "phase10_payload": {"path": str(inputs.phase10_payload_path), "sha256": sha256_file(inputs.phase10_payload_path) if inputs.phase10_payload_path.is_file() else None},
            "candidate_binding": {"path": str(inputs.candidate_binding_path), "sha256": sha256_file(inputs.candidate_binding_path) if inputs.candidate_binding_path.is_file() else None},
            "provider_source_snapshot": {"path": str(inputs.provider_snapshot.path), "sha256": inputs.provider_snapshot.sha256},
            "media_binding_manifest_sha256": media_manifest_sha,
        },
        "prompt_transformations": transformations,
        "cost": dict(pricing) if isinstance(pricing, Mapping) else {},
        "approval_bindings": bindings,
        "missing_approval_types": missing_approvals,
        "technical_blockers": sorted(set(technical_blockers)),
        "actual_provider_call_attempts": 0,
        "generation_call_started": False,
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "mocked": inputs.context.mocked,
        "live": False,
        "claims": {
            "proves": ["one canonical zero-call Phase 11 request body is bound to the ACTIVE_CONSISTENT revision"],
            "does_not_prove": ["provider readiness", "provider submission", "provider acceptance", "returned video"],
        },
    }
    return media_manifest, approval_requirements, live_request


def output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "media_manifest": output_root / "phase11_media_binding_manifest.v2.json",
        "approval_requirements": output_root / "phase11_approval_requirements.v1.json",
        "live_request": output_root / "phase11_live_request.v1.json",
        "validation_receipt": output_root / "phase11_validation_receipt.v1.json",
    }


def write_compiled_bundle(output_root: Path, media: Mapping[str, Any], approvals: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Path]:
    paths = output_paths(output_root)
    write_json(paths["media_manifest"], media)
    write_json(paths["approval_requirements"], approvals)
    write_json(paths["live_request"], request)
    return paths


def phase11_memory_key(run_id: str, revision_id: str) -> str:
    digest = hashlib.sha256(f"persona-dream-phase11\0{run_id}\0{revision_id}".encode("utf-8")).hexdigest()
    return f"pd_phase11_{digest[:48]}"


def memory_document(
    inputs: CompilationInputs,
    *,
    gate_status: str,
    media_file_sha256: str,
    approval_file_sha256: str,
    request_file_sha256: str,
    request_body_sha256: str,
    technical_blockers: Sequence[str],
    missing_approvals: Sequence[str],
) -> dict[str, Any]:
    key = phase11_memory_key(inputs.context.run_id, inputs.context.revision_id)
    document: dict[str, Any] = {
        "_key": key,
        "schema": "persona_dream.phase11_boundary.v1",
        "kind": "persona_dream_phase11_boundary",
        "record_type": "phase11_boundary",
        "project": "persona-dream",
        "run_id": inputs.context.run_id,
        "active_revision_id": inputs.context.revision_id,
        "phase11_revision_id": inputs.context.revision_id,
        "activation_transaction_id": inputs.context.activation_transaction_id,
        "activation_receipt_sha256": sha256_file(inputs.context.activation_receipt_path),
        "media_binding_manifest_sha256": media_file_sha256,
        "approval_requirements_sha256": approval_file_sha256,
        "live_request_file_sha256": request_file_sha256,
        "request_body_sha256": request_body_sha256,
        "provider_source_snapshot_sha256": inputs.provider_snapshot.sha256,
        "gate_status": gate_status,
        "technical_blockers": list(technical_blockers),
        "missing_approval_types": list(missing_approvals),
        "lifecycle_state": "TECHNICALLY_BLOCKED" if technical_blockers else "AWAITING_HUMAN_APPROVAL",
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "actual_provider_call_attempts": 0,
        "scope": f"persona-dream:{inputs.context.run_id}:{inputs.context.revision_id}:phase11",
        "source": f"persona-dream://{inputs.context.run_id}/revisions/{inputs.context.revision_id}/phase11",
        "retrieval_text": (
            f"Persona Dream Phase 11 canonical pre-Kling boundary for run {inputs.context.run_id}, "
            f"active revision {inputs.context.revision_id}. Gate status {gate_status}. "
            f"Technical blockers: {', '.join(technical_blockers) or 'none'}. "
            f"Missing approvals: {', '.join(missing_approvals) or 'none'}. "
            "No provider submission or generation call has occurred."
        ),
        "tags": [
            "persona-dream",
            "phase11",
            f"run:{inputs.context.run_id}",
            f"active-revision:{inputs.context.revision_id}",
            f"gate:{gate_status}",
        ],
    }
    document["document_contract_sha256"] = canonical_sha256(document)
    return document


def response_document(item: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = item.get("doc")
    return nested if isinstance(nested, Mapping) else item


def dense_score(item: Mapping[str, Any]) -> float:
    scores = item.get("scores")
    if not isinstance(scores, Mapping):
        return 0.0
    try:
        return float(scores.get("dense") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def phase11_recall_payload(inputs: CompilationInputs, collection: str) -> dict[str, Any]:
    return {
        "q": (
            "What is the canonical pre-Kling Phase 11 state for Persona Dream "
            f"run {inputs.context.run_id} revision {inputs.context.revision_id}?"
        ),
        "collections": [collection],
        # Memory tag filtering is OR-like across broad tags in current deployments.
        # The active-revision tag alone is the narrow durable identity boundary
        # shared by the active pointer and this exact Phase 11 record.
        "tags": [f"active-revision:{inputs.context.revision_id}"],
        "k": 20,
        "threshold": 0.0,
    }


def validate_phase11_recall_items(items: Any, phase11_key: str) -> dict[str, Any]:
    require(isinstance(items, list), "BLOCKED_PHASE11_MEMORY_RECALL_RESPONSE")
    matches: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        doc = response_document(item)
        if doc.get("_key") == phase11_key:
            matches.append({"key": phase11_key, "dense": dense_score(item)})
    dense_matches = [item for item in matches if item["dense"] > 0.0]
    require(
        dense_matches,
        "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED",
        matching_identity_count=len(matches),
    )
    return {
        "matching_identity_count": len(matches),
        "dense_matching_count": len(dense_matches),
        "max_dense": max(item["dense"] for item in dense_matches),
    }


def persist_phase11_boundary(
    inputs: CompilationInputs,
    document: Mapping[str, Any],
    *,
    memory_url: str,
    collection: str,
    connect_timeout: float,
    read_timeout: float,
) -> dict[str, Any]:
    activation_memory = inputs.context.activation_receipt.get("memory")
    require(isinstance(activation_memory, Mapping), "BLOCKED_MEMORY_ACTIVE_REVISION_UNPROVEN")
    active_key = str(activation_memory.get("active_pointer_key") or "")
    phase11_key = str(document.get("_key") or "")
    with MemoryClient(memory_url, connect_timeout=connect_timeout, read_timeout=read_timeout) as client:
        active_list_payload = {
            "collection": collection,
            "limit": 2,
            "offset": 0,
            "sort_field": "_key",
            "sort_order": "ASC",
            "filters": {"_key": active_key},
        }
        active_evidence = client.post("/list", active_list_payload)
        active_documents = active_evidence.response.get("documents")
        require(isinstance(active_documents, list) and len(active_documents) == 1, "BLOCKED_MEMORY_ACTIVE_POINTER_REREAD_COUNT")
        active_document = active_documents[0]
        require(isinstance(active_document, Mapping), "BLOCKED_MEMORY_ACTIVE_REVISION_UNPROVEN")
        require(active_document.get("active_revision_id") == inputs.context.revision_id, "BLOCKED_MEMORY_ACTIVE_REVISION_CONFLICT")
        require(active_document.get("semantic_sync_state") == "synced", "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED")

        upsert_payload = {"collection": collection, "documents": [dict(document)]}
        upsert_evidence = client.post("/upsert", upsert_payload)
        validate_upsert_result(upsert_evidence, 1)
        list_payload = {
            "collection": collection,
            "limit": 2,
            "offset": 0,
            "sort_field": "_key",
            "sort_order": "ASC",
            "filters": {"_key": phase11_key},
        }
        list_evidence = client.post("/list", list_payload)
        documents = list_evidence.response.get("documents")
        require(isinstance(documents, list) and len(documents) == 1 and isinstance(documents[0], Mapping), "BLOCKED_PHASE11_MEMORY_EXACT_REREAD")
        observed = documents[0]
        forbidden = FORBIDDEN_VECTOR_FIELDS.intersection(observed)
        require(not forbidden, "BLOCKED_MEMORY_INLINE_VECTOR_FORBIDDEN", fields=sorted(forbidden))
        unexpected = set(observed) - set(document) - SERVER_OWNED_FIELDS
        require(not unexpected, "BLOCKED_PHASE11_MEMORY_UNEXPECTED_FIELDS", fields=sorted(unexpected))
        for field, expected in document.items():
            require(observed.get(field) == expected, "BLOCKED_PHASE11_MEMORY_DOCUMENT_MISMATCH", field=field)
        missing_semantic = [field for field in SEMANTIC_REQUIRED_FIELDS if observed.get(field) in (None, "")]
        require(not missing_semantic and observed.get("semantic_sync_state") == "synced", "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED", missing_fields=missing_semantic)

        recall_payload = phase11_recall_payload(inputs, collection)
        recall_evidence = client.post("/recall", recall_payload)
        recall_summary = validate_phase11_recall_items(
            recall_evidence.response.get("items"), phase11_key
        )

    return {
        "persisted": True,
        "collection": collection,
        "phase11_key": phase11_key,
        "active_pointer_key": active_key,
        "active_pointer_exact_reread_count": 1,
        "exact_reread_count": 1,
        "semantic_sync_state": "synced",
        "qdrant_collection": observed.get("qdrant_collection"),
        "qdrant_point_id": observed.get("qdrant_point_id"),
        "embedding_model": observed.get("embedding_model"),
        "embedding_version": observed.get("embedding_version"),
        "text_hash": observed.get("text_hash"),
        "recall": {
            "question": recall_payload["q"],
            "tags": list(recall_payload["tags"]),
            **recall_summary,
        },
        "requests": {
            "active_pointer_list": http_evidence(active_evidence),
            "upsert": http_evidence(upsert_evidence),
            "exact_list": http_evidence(list_evidence),
            "recall": http_evidence(recall_evidence),
        },
    }
