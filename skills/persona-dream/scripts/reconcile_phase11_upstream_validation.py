#!/usr/bin/env python3
"""Correct the historical 12/15 false-green validation for the Phase 11 boundary."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from phase11_canonical_common import (
    Phase11Blocked,
    canonical_sha256,
    now_from_argument,
    portable_run_path,
    read_object,
    resolve_active_context,
    sha256_file,
    validate_schema,
    write_json,
)

DEFERRED_STEPS = [
    {"step_id": "phase11_submit_and_return", "status": "NOT_EXECUTED"},
    {"step_id": "phase12_watch_observation", "status": "NOT_EXECUTED"},
    {"step_id": "phase13_16_cognitive_loop", "status": "NOT_EXECUTED"},
]
CORRECTED_STATUS = "BLOCKED_DOWNSTREAM_NOT_EXECUTED"
CORRECTED_FIRST_BLOCKER = "BLOCKED_PHASE11_PROVIDER_SUBMIT_NOT_EXECUTED"
MIGRATION_RELATIVE = Path("phase_11_submit_return") / "preflight" / "upstream_validation_migration_receipt.json"


def corrected_contract(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": value.get("status"),
        "passed_step_count": value.get("passed_step_count"),
        "step_count": value.get("step_count"),
        "first_blocker": value.get("first_blocker"),
        "phase11_upstream_gate": value.get("phase11_upstream_gate"),
        "upstream_required_step_count": value.get("upstream_required_step_count"),
        "upstream_passed_step_count": value.get("upstream_passed_step_count"),
        "deferred_steps": value.get("deferred_steps"),
        "actual_provider_call_attempts": value.get("actual_provider_call_attempts"),
    }


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def reconcile(run_root: Path, revision_id: str | None, now: str) -> tuple[dict[str, Any], dict[str, Any]]:
    context = resolve_active_context(run_root, revision_id)
    validation_path = context.run_root / "validation.json"
    if not validation_path.is_file():
        raise Phase11Blocked("BLOCKED_UPSTREAM_VALIDATION_MISSING", details={"path": str(validation_path)})
    current = read_object(validation_path)
    migration_path = context.revision_root / MIGRATION_RELATIVE

    already_corrected = (
        current.get("status") == CORRECTED_STATUS
        and current.get("first_blocker") == CORRECTED_FIRST_BLOCKER
        and current.get("phase11_upstream_gate") == "PASS_PHASE11_UPSTREAM_QUALIFIED"
    )
    if already_corrected:
        corrected_sha256 = canonical_sha256(corrected_contract(current))
        if migration_path.is_file():
            receipt = read_object(migration_path)
            errors = validate_schema(receipt, "phase11_upstream_validation_migration.v1.schema.json")
            identity_matches = (
                receipt.get("run_id") == context.run_id
                and receipt.get("revision_id") == context.revision_id
                and receipt.get("activation_transaction_id") == context.activation_transaction_id
            )
            if errors or not identity_matches or receipt.get("corrected_contract_sha256") != corrected_sha256:
                raise Phase11Blocked(
                    "BLOCKED_UPSTREAM_VALIDATION_MIGRATION_RECEIPT_INVALID",
                    details={"errors": errors, "identity_matches": identity_matches},
                )
            return current, receipt

        source_reference = str(current.get("phase11_validation_migration_receipt") or "")
        source_hash = str(current.get("phase11_validation_migration_receipt_sha256") or "")
        if not source_reference:
            raise Phase11Blocked("BLOCKED_UPSTREAM_VALIDATION_MIGRATION_RECEIPT_MISSING")
        source_path = (context.run_root / source_reference).resolve()
        try:
            source_path.relative_to(context.run_root)
        except ValueError as exc:
            raise Phase11Blocked("BLOCKED_UPSTREAM_VALIDATION_MIGRATION_RECEIPT_PATH") from exc
        if not source_path.is_file():
            raise Phase11Blocked(
                "BLOCKED_UPSTREAM_VALIDATION_MIGRATION_RECEIPT_MISSING",
                details={"path": str(source_path)},
            )
        source_receipt = read_object(source_path)
        source_errors = validate_schema(source_receipt, "phase11_upstream_validation_migration.v1.schema.json")
        if source_errors or (source_hash and sha256_file(source_path) != source_hash):
            raise Phase11Blocked(
                "BLOCKED_UPSTREAM_VALIDATION_MIGRATION_SOURCE_INVALID",
                details={"errors": source_errors, "path": str(source_path)},
            )
        if source_receipt.get("corrected_contract_sha256") != corrected_sha256:
            raise Phase11Blocked("BLOCKED_UPSTREAM_VALIDATION_MIGRATION_SOURCE_CONTRACT")

        receipt = dict(source_receipt)
        receipt.update(
            {
                "run_id": context.run_id,
                "revision_id": context.revision_id,
                "activation_transaction_id": context.activation_transaction_id,
                "corrected_contract_sha256": corrected_sha256,
                "reconciled_at": now,
                "actual_provider_call_attempts": 0,
                "provider_live": False,
                "submitted": False,
            }
        )
        errors = validate_schema(receipt, "phase11_upstream_validation_migration.v1.schema.json")
        if errors:
            raise Phase11Blocked(
                "BLOCKED_UPSTREAM_VALIDATION_MIGRATION_RECEIPT_SCHEMA",
                details={"errors": errors},
            )
        write_json(migration_path, receipt)
        current["phase11_validation_migration_receipt"] = portable_run_path(context, migration_path)
        current["phase11_validation_migration_receipt_sha256"] = sha256_file(migration_path)
        atomic_write(validation_path, current)
        return current, receipt

    try:
        passed = int(current.get("passed_step_count") or 0)
        total = int(current.get("step_count") or 0)
    except (TypeError, ValueError) as exc:
        raise Phase11Blocked("BLOCKED_UPSTREAM_VALIDATION_INVALID") from exc
    if passed != 12 or total != 15 or current.get("first_blocker") is not None or str(current.get("status") or "").upper().startswith("BLOCKED"):
        raise Phase11Blocked(
            "BLOCKED_UPSTREAM_VALIDATION_MIGRATION_SOURCE_UNEXPECTED",
            details={"status": current.get("status"), "passed": passed, "total": total, "first_blocker": current.get("first_blocker")},
        )

    source_sha256 = sha256_file(validation_path)
    corrected = dict(current)
    corrected.update(
        {
            "status": CORRECTED_STATUS,
            "first_blocker": CORRECTED_FIRST_BLOCKER,
            "phase11_upstream_gate": "PASS_PHASE11_UPSTREAM_QUALIFIED",
            "upstream_required_step_count": 12,
            "upstream_passed_step_count": 12,
            "deferred_steps": DEFERRED_STEPS,
            "actual_provider_call_attempts": 0,
            "phase11_validation_migration_receipt": portable_run_path(context, migration_path),
        }
    )
    expected_receipt = {
        "schema": "persona_dream.phase11_upstream_validation_migration.v1",
        "status": "PASS_PHASE11_UPSTREAM_VALIDATION_RECONCILED",
        "run_id": context.run_id,
        "revision_id": context.revision_id,
        "activation_transaction_id": context.activation_transaction_id,
        "source_validation_sha256": source_sha256,
        "source_status": current.get("status"),
        "source_passed_step_count": passed,
        "source_step_count": total,
        "source_first_blocker": current.get("first_blocker"),
        "corrected_contract_sha256": canonical_sha256(corrected_contract(corrected)),
        "corrected_status": CORRECTED_STATUS,
        "corrected_first_blocker": CORRECTED_FIRST_BLOCKER,
        "upstream_required_step_count": 12,
        "upstream_passed_step_count": 12,
        "deferred_steps": DEFERRED_STEPS,
        "reconciled_at": now,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "submitted": False,
    }
    if migration_path.is_file():
        receipt = read_object(migration_path)
        for field in (
            "schema",
            "status",
            "run_id",
            "revision_id",
            "activation_transaction_id",
            "source_validation_sha256",
            "corrected_contract_sha256",
            "corrected_status",
            "corrected_first_blocker",
            "deferred_steps",
            "actual_provider_call_attempts",
        ):
            if receipt.get(field) != expected_receipt.get(field):
                raise Phase11Blocked(
                    "BLOCKED_UPSTREAM_VALIDATION_MIGRATION_RECEIPT_CONFLICT",
                    details={"field": field},
                )
    else:
        receipt = expected_receipt
    errors = validate_schema(receipt, "phase11_upstream_validation_migration.v1.schema.json")
    if errors:
        raise Phase11Blocked("BLOCKED_UPSTREAM_VALIDATION_MIGRATION_RECEIPT_SCHEMA", details={"errors": errors})
    if not migration_path.is_file():
        write_json(migration_path, receipt)
    corrected["phase11_validation_migration_receipt_sha256"] = sha256_file(migration_path)
    atomic_write(validation_path, corrected)
    return corrected, receipt


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--run-root", type=Path, required=True)
    value.add_argument("--revision-id")
    value.add_argument("--now")
    value.add_argument("--json", action="store_true")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        now = now_from_argument(args.now).isoformat()
        corrected, receipt = reconcile(args.run_root, args.revision_id, now)
        result = {
            "status": receipt["status"],
            "validation_status": corrected["status"],
            "first_blocker": corrected["first_blocker"],
            "phase11_upstream_gate": corrected["phase11_upstream_gate"],
            "passed_step_count": corrected["passed_step_count"],
            "step_count": corrected["step_count"],
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "submitted": False,
        }
    except Phase11Blocked as exc:
        result = {
            "status": exc.code,
            "details": exc.details,
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "submitted": False,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return exc.exit_code
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
