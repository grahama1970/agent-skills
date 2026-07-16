#!/usr/bin/env python3
"""Activate one verified Persona Dream revision and close its legacy repair queue.

The command is deliberately bounded to the revision-activation transaction. It
never regenerates artifacts, changes creative/provider state, calls fal.ai, or
mutates the historical QUEUED item. Product-visible activation is fail-closed:
run-detail requires the final immutable activation receipt, the terminal queue
event, and every hash-bound local reference before reporting ACTIVE_CONSISTENT.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import stat
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping, Sequence

from prepare_revision_qualification import (
    DEFAULT_COLLECTION,
    DEFAULT_MEMORY_URL,
    FORBIDDEN_VECTOR_FIELDS,
    SEMANTIC_REQUIRED_FIELDS,
    SERVER_OWNED_FIELDS,
    GateBlocked,
    MemoryClient,
    http_evidence,
    load_snapshot,
    read_object,
    sha256_bytes,
    sha256_file,
    sha256_json,
    validate_receipt,
    validate_upsert_result,
)

ACTIVATION_RECEIPT_NAME = "revision_activation_receipt.json"
ACTIVATION_SCHEMA_NAME = "revision_activation_receipt.v1.schema.json"
PREPARE_RECEIPT_NAME = "revision_memory_prepare_receipt.json"
VERIFY_RECEIPT_NAME = "revision_memory_verify_receipt.json"
LOCK_NAME = "revision_activation.lock"
QUEUE_EVENT_NAME = "000001-completed.json"
EXPECTED_COUNTS = {
    "revision": 1,
    "phase": 10,
    "required_artifact": 16,
    "total": 27,
}


# ---------------------------------------------------------------------------
# Stable encoding, path, and immutable-write helpers
# ---------------------------------------------------------------------------


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def pretty_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def require_equal(observed: Any, expected: Any, code: str, **details: Any) -> None:
    if observed != expected:
        raise GateBlocked(
            code,
            details={"expected": expected, "observed": observed, **details},
        )


def require_false_flags(value: Mapping[str, Any], label: str) -> None:
    required = {
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "actual_provider_call_attempts": 0,
    }
    for field, expected in required.items():
        require_equal(
            value.get(field),
            expected,
            "BLOCKED_PROVIDER_INVARIANT_CHANGED",
            document=label,
            field=field,
        )


def expected_evidence_flags(test_fixture: bool) -> dict[str, Any]:
    return {
        "mocked": bool(test_fixture),
        "live": not bool(test_fixture),
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "actual_provider_call_attempts": 0,
    }


def safe_output_path(run_root: Path, relative_path: str) -> Path:
    pure = PurePosixPath(relative_path)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise GateBlocked(
            "BLOCKED_ACTIVATION_OUTPUT_PATH_ESCAPE",
            details={"relative_path": relative_path},
        )

    resolved_root = run_root.resolve(strict=True)
    current = resolved_root
    for part in pure.parts[:-1]:
        current = current / part
        if current.exists():
            mode = os.lstat(current).st_mode
            if stat.S_ISLNK(mode):
                raise GateBlocked(
                    "BLOCKED_ACTIVATION_OUTPUT_SYMLINK",
                    details={"relative_path": relative_path, "component": str(current)},
                )
            if not stat.S_ISDIR(mode):
                raise GateBlocked(
                    "BLOCKED_ACTIVATION_OUTPUT_PARENT_NOT_DIRECTORY",
                    details={"relative_path": relative_path, "component": str(current)},
                )
        else:
            current.mkdir()

    candidate = current / pure.parts[-1]
    try:
        candidate.parent.resolve(strict=True).relative_to(resolved_root)
    except ValueError as exc:
        raise GateBlocked(
            "BLOCKED_ACTIVATION_OUTPUT_PATH_ESCAPE",
            details={"relative_path": relative_path},
        ) from exc
    if candidate.exists() and candidate.is_symlink():
        raise GateBlocked(
            "BLOCKED_ACTIVATION_OUTPUT_SYMLINK",
            details={"relative_path": relative_path, "component": str(candidate)},
        )
    return candidate


def relative_to_run(run_root: Path, path: Path) -> str:
    resolved_root = run_root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        return resolved.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise GateBlocked(
            "BLOCKED_ACTIVATION_REFERENCED_PATH_ESCAPE",
            details={"path": str(path)},
        ) from exc


def local_file_ref(run_root: Path, path: Path) -> dict[str, str]:
    return {
        "relative_path": relative_to_run(run_root, path),
        "sha256": sha256_file(path),
    }


def write_immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = pretty_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing != payload:
            raise GateBlocked(
                "BLOCKED_ACTIVATION_IMMUTABLE_FILE_CONFLICT",
                details={
                    "path": str(path),
                    "existing_sha256": sha256_bytes(existing),
                    "expected_sha256": sha256_bytes(payload),
                },
            )
        return

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise GateBlocked(
                    "BLOCKED_ACTIVATION_IMMUTABLE_FILE_CONFLICT",
                    details={"path": str(path)},
                )
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def activation_lock(run_root: Path) -> Iterator[Path]:
    lock_path = run_root / ".persona-dream" / "state" / LOCK_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.mkdir(lock_path)
    except FileExistsError as exc:
        raise GateBlocked(
            "BLOCKED_REVISION_ACTIVATION_LOCKED",
            details={"path": str(lock_path)},
        ) from exc
    try:
        yield lock_path
    finally:
        try:
            os.rmdir(lock_path)
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Existing prepare/verify receipt chain and local pointer validation
# ---------------------------------------------------------------------------


def assert_live_classification(
    receipt: Mapping[str, Any],
    *,
    test_fixture: bool,
    label: str,
) -> None:
    expected = expected_evidence_flags(test_fixture)
    for field in ("mocked", "live"):
        require_equal(
            receipt.get(field),
            expected[field],
            "BLOCKED_MEMORY_RECEIPT_EVIDENCE_CLASS",
            receipt=label,
            field=field,
        )
    require_false_flags(receipt, label)


def assert_hash_validation(receipt: Mapping[str, Any], snapshot: Any, label: str) -> None:
    validation = receipt.get("hash_validation")
    if not isinstance(validation, Mapping):
        raise GateBlocked(
            "BLOCKED_MEMORY_RECEIPT_HASH_VALIDATION_MISSING",
            details={"receipt": label},
        )
    expected_count = snapshot.hash_validation.artifact_count
    expected = {
        "artifact_count": expected_count,
        "recomputed_count": expected_count,
        "matched_count": expected_count,
        "mismatch_count": 0,
        "symlink_count": 0,
        "escape_count": 0,
        "artifact_hash_manifest_sha256": snapshot.hash_validation.artifact_hash_manifest_sha256,
    }
    for field, expected_value in expected.items():
        require_equal(
            validation.get(field),
            expected_value,
            "BLOCKED_MEMORY_RECEIPT_HASH_VALIDATION_MISMATCH",
            receipt=label,
            field=field,
        )


def assert_record_counts(value: Any, label: str) -> None:
    if not isinstance(value, Mapping):
        raise GateBlocked(
            "BLOCKED_MEMORY_RECEIPT_RECORD_COUNTS_MISSING",
            details={"field": label},
        )
    require_equal(
        dict(value),
        EXPECTED_COUNTS,
        "BLOCKED_MEMORY_RECEIPT_RECORD_COUNTS_MISMATCH",
        field=label,
    )


def assert_semantic_sync(value: Any, label: str) -> None:
    if not isinstance(value, Mapping):
        raise GateBlocked(
            "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED",
            details={"field": label},
            exit_code=3,
        )
    require_equal(
        value.get("required"),
        True,
        "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED",
        field=label,
    )
    require_equal(
        value.get("pointer_count"),
        27,
        "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED",
        field=label,
    )
    states = value.get("states")
    if not isinstance(states, Mapping) or states.get("synced") != 27:
        raise GateBlocked(
            "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED",
            details={"field": label, "states": states},
            exit_code=3,
        )


def validate_prepare_verify_chain(
    snapshot: Any,
    args: argparse.Namespace,
) -> dict[str, Any]:
    prepare_path = snapshot.revision_root / PREPARE_RECEIPT_NAME
    verify_path = snapshot.revision_root / VERIFY_RECEIPT_NAME
    if not prepare_path.is_file():
        raise GateBlocked(
            "BLOCKED_MEMORY_PREPARE_RECEIPT_MISSING",
            details={"path": str(prepare_path)},
        )
    if not verify_path.is_file():
        raise GateBlocked(
            "BLOCKED_MEMORY_VERIFY_RECEIPT_MISSING",
            details={"path": str(verify_path)},
        )

    prepare_receipt = read_object(prepare_path)
    verify_receipt = read_object(verify_path)
    validate_receipt(prepare_receipt, "revision_memory_prepare_receipt.v1.schema.json")
    validate_receipt(verify_receipt, "revision_memory_verify_receipt.v1.schema.json")

    shared_expected = {
        "run_id": snapshot.run_id,
        "revision_id": snapshot.revision_id,
        "source_revision_id": snapshot.source_revision_id,
        "source_commit": snapshot.source_commit,
        "runtime_release_id": snapshot.runtime_release_id,
        "memory_url": args.memory_url.rstrip("/"),
        "collection": args.collection,
        "artifact_index_sha256": snapshot.index_sha256,
        "revision_manifest_sha256": snapshot.manifest_sha256,
        "actual_provider_call_attempts": 0,
    }
    for label, receipt, status, lifecycle in (
        (
            "prepare",
            prepare_receipt,
            "PASS_MEMORY_REVISION_PREPARED",
            "PREPARED",
        ),
        (
            "verify",
            verify_receipt,
            "PASS_MEMORY_REVISION_VERIFIED",
            "VERIFIED",
        ),
    ):
        require_equal(
            receipt.get("status"),
            status,
            "BLOCKED_MEMORY_RECEIPT_STATUS",
            receipt=label,
        )
        require_equal(
            receipt.get("lifecycle_state"),
            lifecycle,
            "BLOCKED_MEMORY_RECEIPT_LIFECYCLE",
            receipt=label,
        )
        for field, expected_value in shared_expected.items():
            require_equal(
                receipt.get(field),
                expected_value,
                "BLOCKED_MEMORY_RECEIPT_IDENTITY_MISMATCH",
                receipt=label,
                field=field,
            )
        assert_live_classification(
            receipt,
            test_fixture=args.test_fixture,
            label=label,
        )
        assert_hash_validation(receipt, snapshot, label)

    prepare_sha256 = sha256_file(prepare_path)
    verify_sha256 = sha256_file(verify_path)
    require_equal(
        verify_receipt.get("prepare_receipt_sha256"),
        prepare_sha256,
        "BLOCKED_MEMORY_RECEIPT_HASH_CHAIN",
        field="verify.prepare_receipt_sha256",
    )

    prepare_records = prepare_receipt.get("records")
    verify_records = verify_receipt.get("records")
    if not isinstance(prepare_records, Mapping) or not isinstance(verify_records, Mapping):
        raise GateBlocked("BLOCKED_MEMORY_RECEIPT_RECORDS_MISSING")
    for field in ("expected_counts", "returned_counts"):
        assert_record_counts(prepare_records.get(field), f"prepare.records.{field}")
    for field in ("expected_counts", "before_counts", "after_counts"):
        assert_record_counts(verify_records.get(field), f"verify.records.{field}")
    require_equal(
        prepare_records.get("exact_keys"),
        verify_records.get("exact_keys"),
        "BLOCKED_MEMORY_RECEIPT_EXACT_KEYS_MISMATCH",
    )

    assert_semantic_sync(prepare_receipt.get("semantic_sync"), "prepare.semantic_sync")
    verify_semantic = verify_receipt.get("semantic_sync")
    if not isinstance(verify_semantic, Mapping):
        raise GateBlocked(
            "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED",
            exit_code=3,
        )
    assert_semantic_sync(verify_semantic.get("before"), "verify.semantic_sync.before")
    assert_semantic_sync(verify_semantic.get("after"), "verify.semantic_sync.after")
    recall = verify_semantic.get("recall")
    if not isinstance(recall, Mapping):
        raise GateBlocked("BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED", exit_code=3)
    try:
        max_dense = float(recall.get("max_dense") or 0.0)
        dense_count = int(recall.get("dense_matching_count") or 0)
        identity_count = int(recall.get("matching_identity_count") or 0)
    except (TypeError, ValueError) as exc:
        raise GateBlocked("BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED", exit_code=3) from exc
    if max_dense <= 0.0 or dense_count < 1 or identity_count < 1:
        raise GateBlocked(
            "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED",
            details={
                "max_dense": max_dense,
                "dense_matching_count": dense_count,
                "matching_identity_count": identity_count,
            },
            exit_code=3,
        )

    return {
        "prepare_path": prepare_path,
        "prepare_receipt": prepare_receipt,
        "prepare_sha256": prepare_sha256,
        "verify_path": verify_path,
        "verify_receipt": verify_receipt,
        "verify_sha256": verify_sha256,
        "runtime_release_id": str(verify_receipt["runtime_release_id"]),
        "exact_keys": list(verify_records["exact_keys"]),
        "max_dense": max_dense,
        "dense_matching_count": dense_count,
    }


def validate_local_pointer(snapshot: Any) -> dict[str, Any]:
    pointer_path = snapshot.run_root / ".persona-dream" / "state" / "active_revision.json"
    if not pointer_path.is_file():
        raise GateBlocked(
            "BLOCKED_ACTIVE_REVISION_MISSING",
            details={"path": str(pointer_path)},
        )
    pointer = read_object(pointer_path)
    if pointer.get("schemaVersion") not in {
        "persona_dream.active_revision_pointer.v1",
        "persona_dream.active_revision_pointer.v2",
    }:
        raise GateBlocked(
            "BLOCKED_LOCAL_ACTIVE_POINTER_SCHEMA",
            details={"observed": pointer.get("schemaVersion")},
        )
    expected = {
        "runId": snapshot.run_id,
        "revisionId": snapshot.revision_id,
        "revisionManifestSha256": snapshot.manifest_sha256,
    }
    for field, expected_value in expected.items():
        require_equal(
            pointer.get(field),
            expected_value,
            "BLOCKED_LOCAL_ACTIVE_POINTER_MISMATCH",
            field=field,
        )
    return {
        "path": pointer_path,
        "value": pointer,
        "sha256": sha256_file(pointer_path),
    }


# ---------------------------------------------------------------------------
# Legacy queue/work-order validation and deterministic terminal event
# ---------------------------------------------------------------------------


def validate_repair_queue(snapshot: Any) -> dict[str, Any]:
    queue_root = snapshot.run_root / ".persona-dream" / "repair" / "tau-queue"
    if not queue_root.is_dir():
        raise GateBlocked(
            "BLOCKED_REPAIR_QUEUE_MISSING",
            details={"path": str(queue_root)},
        )

    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(queue_root.glob("*.json")):
        value = read_object(path)
        embedded = value.get("workOrder")
        if not isinstance(embedded, Mapping):
            continue
        if (
            embedded.get("runId") == snapshot.run_id
            and embedded.get("targetRevisionId") == snapshot.revision_id
        ):
            matches.append((path, value))
    if len(matches) != 1:
        raise GateBlocked(
            "BLOCKED_REPAIR_QUEUE_IDENTITY",
            details={"matching_queue_items": [str(path) for path, _ in matches]},
        )

    queue_path, queue_item = matches[0]
    require_equal(
        queue_item.get("schemaVersion"),
        "persona_dream.tau_repair_queue_item.v1",
        "BLOCKED_REPAIR_QUEUE_SCHEMA",
    )
    require_equal(
        queue_item.get("status"),
        "QUEUED",
        "BLOCKED_REPAIR_QUEUE_STATE",
    )
    embedded = queue_item.get("workOrder")
    assert isinstance(embedded, Mapping)
    work_order_id = str(embedded.get("workOrderId") or "")
    if not work_order_id:
        raise GateBlocked("BLOCKED_REPAIR_WORK_ORDER_ID_MISSING")

    work_order_path = (
        snapshot.run_root
        / ".persona-dream"
        / "repair"
        / "work-orders"
        / f"{work_order_id}.json"
    )
    if not work_order_path.is_file():
        raise GateBlocked(
            "BLOCKED_REPAIR_WORK_ORDER_MISSING",
            details={"path": str(work_order_path)},
        )
    work_order = read_object(work_order_path)
    require_equal(
        sha256_json(work_order),
        sha256_json(dict(embedded)),
        "BLOCKED_REPAIR_WORK_ORDER_EMBEDDED_MISMATCH",
    )

    expected = {
        "schemaVersion": "persona_dream.repair_work_order.v1",
        "workOrderId": work_order_id,
        "runId": snapshot.run_id,
        "sourceRevisionId": snapshot.source_revision_id,
        "targetRevisionId": snapshot.revision_id,
        "status": "REQUESTED",
    }
    for field, expected_value in expected.items():
        require_equal(
            work_order.get(field),
            expected_value,
            "BLOCKED_REPAIR_WORK_ORDER_IDENTITY",
            field=field,
        )
    detection = work_order.get("detection")
    policy = work_order.get("policy")
    if not isinstance(detection, Mapping) or not isinstance(policy, Mapping):
        raise GateBlocked("BLOCKED_REPAIR_WORK_ORDER_CONTRACT")
    require_equal(
        detection.get("selectedThroughPhase"),
        "10",
        "BLOCKED_REPAIR_WORK_ORDER_SCOPE",
    )
    require_equal(
        policy.get("stopBeforePhase"),
        "11",
        "BLOCKED_REPAIR_WORK_ORDER_SCOPE",
    )
    forbidden = set(policy.get("forbiddenSideEffects") or [])
    required_forbidden = {
        "external_network",
        "public_media_publication",
        "paid_provider_call",
        "provider_submission",
        "human_acceptance_fabrication",
    }
    if not required_forbidden.issubset(forbidden):
        raise GateBlocked(
            "BLOCKED_REPAIR_WORK_ORDER_SIDE_EFFECT_POLICY",
            details={"missing": sorted(required_forbidden - forbidden)},
        )

    event_relative_path = (
        PurePosixPath(".persona-dream")
        / "repair"
        / "queue-events"
        / work_order_id
        / QUEUE_EVENT_NAME
    ).as_posix()
    event_path = safe_output_path(snapshot.run_root, event_relative_path)
    return {
        "queue_path": queue_path,
        "queue_item": queue_item,
        "queue_sha256": sha256_file(queue_path),
        "work_order_path": work_order_path,
        "work_order": work_order,
        "work_order_sha256": sha256_file(work_order_path),
        "work_order_id": work_order_id,
        "event_path": event_path,
        "event_relative_path": event_relative_path,
    }


def active_pointer_key(run_id: str) -> str:
    digest = hashlib.sha256(f"persona-dream-active\0{run_id}".encode("utf-8")).hexdigest()
    return f"pd_active_{digest[:48]}"


def activation_transaction_id(
    snapshot: Any,
    chain: Mapping[str, Any],
    pointer: Mapping[str, Any],
    queue: Mapping[str, Any],
) -> str:
    value = {
        "run_id": snapshot.run_id,
        "revision_id": snapshot.revision_id,
        "source_revision_id": snapshot.source_revision_id,
        "source_commit": snapshot.source_commit,
        "revision_manifest_sha256": snapshot.manifest_sha256,
        "artifact_index_sha256": snapshot.index_sha256,
        "prepare_receipt_sha256": chain["prepare_sha256"],
        "verify_receipt_sha256": chain["verify_sha256"],
        "local_active_pointer_sha256": pointer["sha256"],
        "work_order_sha256": queue["work_order_sha256"],
        "queue_item_sha256": queue["queue_sha256"],
    }
    return f"activation-{sha256_json(value).removeprefix('sha256:')[:32]}"


def terminal_event(
    snapshot: Any,
    chain: Mapping[str, Any],
    pointer: Mapping[str, Any],
    queue: Mapping[str, Any],
    *,
    transaction_id: str,
    active_key: str,
    activated_at: str,
    test_fixture: bool,
) -> dict[str, Any]:
    return {
        "schema": "persona_dream.repair_queue_terminal_event.v1",
        "status": "COMPLETED",
        "event_type": "REPAIR_COMPLETED",
        "sequence": 1,
        "activation_transaction_id": transaction_id,
        "run_id": snapshot.run_id,
        "work_order_id": queue["work_order_id"],
        "source_revision_id": snapshot.source_revision_id,
        "target_revision_id": snapshot.revision_id,
        "historical_queue_status": "QUEUED",
        "memory_active_pointer_key": active_key,
        "prepare_receipt_sha256": chain["prepare_sha256"],
        "verify_receipt_sha256": chain["verify_sha256"],
        "revision_manifest_sha256": snapshot.manifest_sha256,
        "artifact_index_sha256": snapshot.index_sha256,
        "local_active_pointer_sha256": pointer["sha256"],
        "work_order_sha256": queue["work_order_sha256"],
        "queue_item_sha256": queue["queue_sha256"],
        "occurred_at": activated_at,
        **expected_evidence_flags(test_fixture),
    }


# ---------------------------------------------------------------------------
# Memory active-pointer transaction
# ---------------------------------------------------------------------------


def list_active_pointer(
    client: MemoryClient,
    collection: str,
    key: str,
) -> tuple[list[dict[str, Any]], Any]:
    payload = {
        "collection": collection,
        "limit": 2,
        "offset": 0,
        "sort_field": "_key",
        "sort_order": "ASC",
        "filters": {"_key": key},
    }
    evidence = client.post("/list", payload)
    documents = evidence.response.get("documents")
    if not isinstance(documents, list) or not all(isinstance(item, dict) for item in documents):
        raise GateBlocked(
            "BLOCKED_MEMORY_ACTIVE_POINTER_LIST_INVALID",
            details={"response": evidence.response},
            exit_code=4,
        )
    if len(documents) > 1:
        raise GateBlocked(
            "BLOCKED_MEMORY_ACTIVE_POINTER_DUPLICATE",
            details={"count": len(documents)},
        )
    return [dict(item) for item in documents], evidence


def pointer_document(
    snapshot: Any,
    chain: Mapping[str, Any],
    local_pointer: Mapping[str, Any],
    queue: Mapping[str, Any],
    *,
    active_key: str,
    transaction_id: str,
    queue_event_sha256: str,
    activated_at: str,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "_key": active_key,
        "schema": "persona_dream.active_revision_pointer.v1",
        "kind": "persona_dream_active_revision_pointer",
        "record_type": "active_revision_pointer",
        "project": "persona-dream",
        "run_id": snapshot.run_id,
        "active_revision_id": snapshot.revision_id,
        "previous_revision_id": snapshot.source_revision_id,
        "source_commit": snapshot.source_commit,
        "runtime_release_id": chain["runtime_release_id"],
        "lifecycle_state": "ACTIVE",
        "qualification_status": "MEMORY_ACTIVE_POINTER_WRITTEN",
        "activation_receipt_required": True,
        "activation_receipt_relative_path": (
            PurePosixPath(".persona-dream")
            / "revisions"
            / snapshot.revision_id
            / ACTIVATION_RECEIPT_NAME
        ).as_posix(),
        "activation_transaction_id": transaction_id,
        "revision_manifest_sha256": snapshot.manifest_sha256,
        "artifact_index_sha256": snapshot.index_sha256,
        "local_active_pointer_sha256": local_pointer["sha256"],
        "prepare_receipt_sha256": chain["prepare_sha256"],
        "verify_receipt_sha256": chain["verify_sha256"],
        "work_order_sha256": queue["work_order_sha256"],
        "queue_item_sha256": queue["queue_sha256"],
        "queue_terminal_event_sha256": queue_event_sha256,
        "activated_at": activated_at,
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "actual_provider_call_attempts": 0,
        "scope": f"persona-dream:{snapshot.run_id}:active-revision",
        "source": f"persona-dream://{snapshot.run_id}/active-revision",
        "retrieval_text": (
            f"The active immutable Persona Dream revision for run {snapshot.run_id} "
            f"is {snapshot.revision_id}. Memory verification passed for Phase 01 "
            "through Phase 10, the historical repair work order reached a hash-bound "
            "terminal event, and provider calls remain disabled."
        ),
        "tags": [
            "persona-dream",
            "active-revision-pointer",
            f"run:{snapshot.run_id}",
            f"active-revision:{snapshot.revision_id}",
        ],
    }
    document["document_contract_sha256"] = sha256_json(document)
    return document


def assert_pointer_document(
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
) -> dict[str, Any]:
    forbidden = FORBIDDEN_VECTOR_FIELDS.intersection(observed)
    if forbidden:
        raise GateBlocked(
            "BLOCKED_MEMORY_INLINE_VECTOR_FORBIDDEN",
            details={"key": expected.get("_key"), "fields": sorted(forbidden)},
        )
    unexpected = set(observed) - set(expected) - SERVER_OWNED_FIELDS
    if unexpected:
        raise GateBlocked(
            "BLOCKED_MEMORY_ACTIVE_POINTER_UNEXPECTED_FIELDS",
            details={"fields": sorted(unexpected)},
        )
    for field, expected_value in expected.items():
        require_equal(
            observed.get(field),
            expected_value,
            "BLOCKED_MEMORY_ACTIVE_POINTER_MISMATCH",
            field=field,
        )
    missing = [field for field in SEMANTIC_REQUIRED_FIELDS if observed.get(field) in (None, "")]
    if missing or observed.get("semantic_sync_state") != "synced":
        raise GateBlocked(
            "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED",
            details={
                "missing_fields": missing,
                "semantic_sync_state": observed.get("semantic_sync_state"),
                "semantic_sync_error": observed.get("semantic_sync_error"),
            },
            exit_code=3,
        )
    return {
        "qdrant_collection": str(observed["qdrant_collection"]),
        "qdrant_point_id": str(observed["qdrant_point_id"]),
        "embedding_model": str(observed["embedding_model"]),
        "embedding_version": str(observed["embedding_version"]),
        "text_hash": str(observed["text_hash"]),
        "semantic_sync_state": str(observed["semantic_sync_state"]),
    }


def validate_existing_pointer_state(
    documents: Sequence[Mapping[str, Any]],
    snapshot: Any,
) -> str | None:
    if not documents:
        return None
    document = documents[0]
    require_equal(
        document.get("run_id"),
        snapshot.run_id,
        "BLOCKED_MEMORY_ACTIVE_POINTER_IDENTITY",
        field="run_id",
    )
    active_revision_id = str(document.get("active_revision_id") or "")
    if active_revision_id not in {snapshot.source_revision_id, snapshot.revision_id}:
        raise GateBlocked(
            "BLOCKED_MEMORY_ACTIVE_REVISION_CONFLICT",
            details={
                "expected_source_revision_id": snapshot.source_revision_id,
                "target_revision_id": snapshot.revision_id,
                "observed_active_revision_id": active_revision_id,
            },
        )
    return active_revision_id


# ---------------------------------------------------------------------------
# Activation receipt
# ---------------------------------------------------------------------------


def command_metadata(source_commit: str) -> dict[str, Any]:
    script_path = Path(__file__).resolve()
    return {
        "argv": list(sys.argv),
        "cwd": str(Path.cwd()),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "script_path": str(script_path),
        "script_sha256": sha256_file(script_path),
        "source_commit": source_commit,
    }


def make_file_refs(
    snapshot: Any,
    chain: Mapping[str, Any],
    pointer: Mapping[str, Any],
    queue: Mapping[str, Any],
    event_path: Path,
) -> dict[str, dict[str, str]]:
    return {
        "revision_manifest": local_file_ref(snapshot.run_root, snapshot.manifest_path),
        "artifact_index": local_file_ref(snapshot.run_root, snapshot.index_path),
        "prepare_receipt": local_file_ref(snapshot.run_root, chain["prepare_path"]),
        "verify_receipt": local_file_ref(snapshot.run_root, chain["verify_path"]),
        "local_active_pointer": local_file_ref(snapshot.run_root, pointer["path"]),
        "work_order": local_file_ref(snapshot.run_root, queue["work_order_path"]),
        "queue_item": local_file_ref(snapshot.run_root, queue["queue_path"]),
        "queue_terminal_event": local_file_ref(snapshot.run_root, event_path),
    }


def validate_existing_activation_receipt(
    receipt: Mapping[str, Any],
    *,
    snapshot: Any,
    args: argparse.Namespace,
    transaction_id: str,
    active_key: str,
    file_refs: Mapping[str, Any],
    semantic_pointer: Mapping[str, Any],
    queue: Mapping[str, Any],
) -> None:
    validate_receipt(receipt, ACTIVATION_SCHEMA_NAME)
    expected = {
        "status": "PASS_ACTIVE_CONSISTENT",
        "run_id": snapshot.run_id,
        "revision_id": snapshot.revision_id,
        "source_revision_id": snapshot.source_revision_id,
        "source_commit": snapshot.source_commit,
        "memory_url": args.memory_url.rstrip("/"),
        "collection": args.collection,
        "activation_transaction_id": transaction_id,
        "actual_provider_call_attempts": 0,
    }
    for field, expected_value in expected.items():
        require_equal(
            receipt.get(field),
            expected_value,
            "BLOCKED_ACTIVATION_RECEIPT_STALE",
            field=field,
        )
    assert_live_classification(
        receipt,
        test_fixture=args.test_fixture,
        label="activation",
    )
    require_equal(
        receipt.get("local_files"),
        file_refs,
        "BLOCKED_ACTIVATION_RECEIPT_LOCAL_FILES_MISMATCH",
    )
    memory = receipt.get("memory")
    if not isinstance(memory, Mapping):
        raise GateBlocked("BLOCKED_ACTIVATION_RECEIPT_MEMORY_MISSING")
    require_equal(
        memory.get("active_pointer_key"),
        active_key,
        "BLOCKED_ACTIVATION_RECEIPT_MEMORY_MISMATCH",
    )
    require_equal(
        memory.get("active_revision_id"),
        snapshot.revision_id,
        "BLOCKED_ACTIVATION_RECEIPT_MEMORY_MISMATCH",
    )
    for field, expected_value in semantic_pointer.items():
        require_equal(
            memory.get(field),
            expected_value,
            "BLOCKED_ACTIVATION_RECEIPT_MEMORY_MISMATCH",
            field=field,
        )
    queue_value = receipt.get("queue")
    if not isinstance(queue_value, Mapping):
        raise GateBlocked("BLOCKED_ACTIVATION_RECEIPT_QUEUE_MISSING")
    require_equal(
        queue_value.get("work_order_id"),
        queue["work_order_id"],
        "BLOCKED_ACTIVATION_RECEIPT_QUEUE_MISMATCH",
    )
    require_equal(
        queue_value.get("terminal_status"),
        "COMPLETED",
        "BLOCKED_ACTIVATION_RECEIPT_QUEUE_MISMATCH",
    )


def activation_receipt(
    snapshot: Any,
    args: argparse.Namespace,
    chain: Mapping[str, Any],
    local_pointer: Mapping[str, Any],
    queue: Mapping[str, Any],
    *,
    transaction_id: str,
    active_key: str,
    activated_at: str,
    file_refs: Mapping[str, Any],
    semantic_pointer: Mapping[str, Any],
    list_before: Any,
    upsert: Any,
    list_after: Any,
) -> dict[str, Any]:
    return {
        "schema": "persona_dream.revision_activation_receipt.v1",
        "status": "PASS_ACTIVE_CONSISTENT",
        "gate": "revision-activation-and-repair-queue-convergence",
        "run_id": snapshot.run_id,
        "revision_id": snapshot.revision_id,
        "source_revision_id": snapshot.source_revision_id,
        "source_commit": snapshot.source_commit,
        "runtime_release_id": chain["runtime_release_id"],
        "memory_url": args.memory_url.rstrip("/"),
        "collection": args.collection,
        "activation_transaction_id": transaction_id,
        "activated_at": activated_at,
        "local_files": dict(file_refs),
        "local_pointer": {
            "schema_version": local_pointer["value"].get("schemaVersion"),
            "run_id": snapshot.run_id,
            "revision_id": snapshot.revision_id,
            "revision_manifest_sha256": snapshot.manifest_sha256,
        },
        "receipt_chain": {
            "prepare_schema": "persona_dream.revision_memory_prepare_receipt.v1",
            "prepare_status": "PASS_MEMORY_REVISION_PREPARED",
            "verify_schema": "persona_dream.revision_memory_verify_receipt.v1",
            "verify_status": "PASS_MEMORY_REVISION_VERIFIED",
            "exact_record_count": 27,
            "phase_record_count": 10,
            "required_artifact_record_count": 16,
            "semantic_pointer_count": 27,
            "dense_matching_count": chain["dense_matching_count"],
            "max_dense": chain["max_dense"],
        },
        "memory": {
            "active_pointer_key": active_key,
            "active_revision_id": snapshot.revision_id,
            "previous_revision_id": snapshot.source_revision_id,
            "exact_reread_count": 1,
            "document_contract_sha256": semantic_pointer["document_contract_sha256"],
            "qdrant_collection": semantic_pointer["qdrant_collection"],
            "qdrant_point_id": semantic_pointer["qdrant_point_id"],
            "embedding_model": semantic_pointer["embedding_model"],
            "embedding_version": semantic_pointer["embedding_version"],
            "text_hash": semantic_pointer["text_hash"],
            "semantic_sync_state": semantic_pointer["semantic_sync_state"],
            "requests": {
                "list_before": http_evidence(list_before),
                "upsert": http_evidence(upsert),
                "list_after": http_evidence(list_after),
            },
        },
        "queue": {
            "work_order_id": queue["work_order_id"],
            "source_revision_id": snapshot.source_revision_id,
            "target_revision_id": snapshot.revision_id,
            "historical_queue_status": "QUEUED",
            "terminal_status": "COMPLETED",
            "terminal_event_schema": "persona_dream.repair_queue_terminal_event.v1",
            "terminal_event_sequence": 1,
        },
        "hash_validation": {
            "artifact_count": snapshot.hash_validation.artifact_count,
            "recomputed_count": snapshot.hash_validation.recomputed_count,
            "matched_count": snapshot.hash_validation.matched_count,
            "mismatch_count": snapshot.hash_validation.mismatch_count,
            "symlink_count": snapshot.hash_validation.symlink_count,
            "escape_count": snapshot.hash_validation.escape_count,
            "artifact_hash_manifest_sha256": snapshot.hash_validation.artifact_hash_manifest_sha256,
        },
        "command": command_metadata(snapshot.source_commit),
        "claims": {
            "proves": [
                "Memory exactly re-read one synced run-scoped active revision pointer",
                "the immutable local pointer, Memory prepare/verify receipts, work order, historical queue item, and terminal event are hash-bound",
                "the historical QUEUED item was preserved and an immutable COMPLETED event was appended",
            ],
            "does_not_prove": [
                "provider readiness, publication, payment, or provider submission",
                "Watch, interpretation, Theory-of-Mind, or durable persona behavior",
                "repair regeneration or creative-media changes",
            ],
        },
        **expected_evidence_flags(args.test_fixture),
    }


# ---------------------------------------------------------------------------
# Main transaction
# ---------------------------------------------------------------------------


def activate(args: argparse.Namespace) -> dict[str, Any]:
    snapshot = load_snapshot(args.run_root, args.revision_id, args.source_commit)
    chain = validate_prepare_verify_chain(snapshot, args)
    local_pointer = validate_local_pointer(snapshot)
    queue = validate_repair_queue(snapshot)
    active_key = active_pointer_key(snapshot.run_id)
    transaction_id = activation_transaction_id(snapshot, chain, local_pointer, queue)
    receipt_path = snapshot.revision_root / ACTIVATION_RECEIPT_NAME

    with activation_lock(snapshot.run_root):
        with MemoryClient(
            args.memory_url,
            connect_timeout=args.connect_timeout,
            read_timeout=args.read_timeout,
        ) as client:
            existing_documents, list_before = list_active_pointer(
                client, args.collection, active_key
            )
            existing_state = validate_existing_pointer_state(existing_documents, snapshot)
            existing = existing_documents[0] if existing_documents else None
            existing_receipt = read_object(receipt_path) if receipt_path.is_file() else None
            if existing_receipt is not None:
                validate_receipt(existing_receipt, ACTIVATION_SCHEMA_NAME)
                if existing_state != snapshot.revision_id or existing is None:
                    raise GateBlocked("BLOCKED_MEMORY_ACTIVE_POINTER_MISSING")
                activated_at = str(existing_receipt.get("activated_at") or "")
            elif existing_state == snapshot.revision_id:
                activated_at = str(existing.get("activated_at") or "") if existing else ""
            else:
                activated_at = utc_now()
            if not activated_at:
                raise GateBlocked(
                    "BLOCKED_MEMORY_ACTIVE_POINTER_MISMATCH",
                    details={"field": "activated_at"},
                )

            event = terminal_event(
                snapshot,
                chain,
                local_pointer,
                queue,
                transaction_id=transaction_id,
                active_key=active_key,
                activated_at=activated_at,
                test_fixture=args.test_fixture,
            )
            event_payload = pretty_json_bytes(event)
            event_sha256 = sha256_bytes(event_payload)
            expected_pointer = pointer_document(
                snapshot,
                chain,
                local_pointer,
                queue,
                active_key=active_key,
                transaction_id=transaction_id,
                queue_event_sha256=event_sha256,
                activated_at=activated_at,
            )
            if existing_state == snapshot.revision_id and existing:
                # An already-targeted Memory pointer is recoverable only when it
                # is the exact same activation transaction. Never overwrite a
                # target pointer whose evidence hashes changed.
                assert_pointer_document(expected_pointer, existing)

            if receipt_path.is_file():
                if not queue["event_path"].is_file():
                    raise GateBlocked(
                        "BLOCKED_QUEUE_TERMINAL_EVENT_MISSING",
                        details={"path": str(queue["event_path"])},
                    )
                existing_event_payload = queue["event_path"].read_bytes()
                if existing_event_payload != event_payload:
                    raise GateBlocked(
                        "BLOCKED_QUEUE_TERMINAL_EVENT_MISMATCH",
                        details={
                            "existing_sha256": sha256_bytes(existing_event_payload),
                            "expected_sha256": event_sha256,
                        },
                    )
                if not existing:
                    raise GateBlocked("BLOCKED_MEMORY_ACTIVE_POINTER_MISSING")
                semantic_pointer = assert_pointer_document(expected_pointer, existing)
                semantic_pointer["document_contract_sha256"] = str(
                    existing["document_contract_sha256"]
                )
                file_refs = make_file_refs(
                    snapshot, chain, local_pointer, queue, queue["event_path"]
                )
                assert existing_receipt is not None
                validate_existing_activation_receipt(
                    existing_receipt,
                    snapshot=snapshot,
                    args=args,
                    transaction_id=transaction_id,
                    active_key=active_key,
                    file_refs=file_refs,
                    semantic_pointer=semantic_pointer,
                    queue=queue,
                )
                return existing_receipt

            upsert_payload = {
                "collection": args.collection,
                "documents": [expected_pointer],
            }
            upsert_evidence = client.post("/upsert", upsert_payload)
            validate_upsert_result(upsert_evidence, 1)
            observed_documents, list_after = list_active_pointer(
                client, args.collection, active_key
            )
            if len(observed_documents) != 1:
                raise GateBlocked(
                    "BLOCKED_MEMORY_ACTIVE_POINTER_REREAD_COUNT",
                    details={"count": len(observed_documents)},
                )
            semantic_pointer = assert_pointer_document(
                expected_pointer, observed_documents[0]
            )
            semantic_pointer["document_contract_sha256"] = str(
                observed_documents[0]["document_contract_sha256"]
            )

        # Memory is durable and exactly re-read before the local terminal event.
        # Until the final receipt exists, run-detail remains LEGACY_UNQUALIFIED.
        write_immutable_json(queue["event_path"], event)
        require_equal(
            sha256_file(queue["event_path"]),
            event_sha256,
            "BLOCKED_QUEUE_TERMINAL_EVENT_HASH_MISMATCH",
        )
        file_refs = make_file_refs(
            snapshot, chain, local_pointer, queue, queue["event_path"]
        )
        receipt = activation_receipt(
            snapshot,
            args,
            chain,
            local_pointer,
            queue,
            transaction_id=transaction_id,
            active_key=active_key,
            activated_at=activated_at,
            file_refs=file_refs,
            semantic_pointer=semantic_pointer,
            list_before=list_before,
            upsert=upsert_evidence,
            list_after=list_after,
        )
        validate_receipt(receipt, ACTIVATION_SCHEMA_NAME)
        write_immutable_json(receipt_path, receipt)
        return receipt


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--run-root", type=Path, required=True)
    value.add_argument("--revision-id", required=True)
    value.add_argument("--source-commit", required=True)
    value.add_argument("--memory-url", default=DEFAULT_MEMORY_URL)
    value.add_argument("--collection", default=DEFAULT_COLLECTION)
    value.add_argument("--connect-timeout", type=float, default=5.0)
    value.add_argument("--read-timeout", type=float, default=60.0)
    value.add_argument("--test-fixture", action="store_true", help=argparse.SUPPRESS)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = activate(args)
    except GateBlocked as exc:
        output = {
            "status": exc.code,
            "gate": "revision-activation-and-repair-queue-convergence",
            "details": exc.details,
            **expected_evidence_flags(args.test_fixture),
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return exc.exit_code
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
