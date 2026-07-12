#!/usr/bin/env python3
"""Aggregate Phase 11 metadata, approval templates, and the zero-call submit gate."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def write_object(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def build_bundle(
    phase10_receipt_path: Path,
    schema_receipt_path: Path,
    fal_preflight_path: Path,
    media_manifest_path: Path,
    revision_id: str,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    current = now or datetime.now(timezone.utc)
    phase10 = read_object(phase10_receipt_path)
    schema = read_object(schema_receipt_path)
    preflight = read_object(fal_preflight_path)
    media = read_object(media_manifest_path)
    endpoint = str(schema.get("model_endpoint") or phase10.get("endpoint") or "")
    provider = str(schema.get("provider") or "kling")
    source_urls = schema.get("source_urls") if isinstance(schema.get("source_urls"), list) else []
    schema_generated = str(schema.get("generated_at") or "")
    schema_time = datetime.fromisoformat(schema_generated.replace("Z", "+00:00")) if schema_generated else current
    dry_expires = schema_time + timedelta(days=7)
    live_expires = schema_time + timedelta(hours=24)
    schema_payload = json.dumps(schema.get("observed_schema") or {}, sort_keys=True, separators=(",", ":")).encode()
    metadata_blockers: list[str] = []
    if preflight.get("status") != "PASS_FAL_API_PREFLIGHT":
        metadata_blockers.append("BLOCKED_FAL_API_PREFLIGHT")
    if schema.get("status") != "PASS_PROVIDER_SCHEMA_DRY_RUN_REVIEWED":
        metadata_blockers.append("BLOCKED_PROVIDER_SCHEMA_RECEIPT")
    if current > dry_expires:
        metadata_blockers.append("BLOCKED_PROVIDER_SCHEMA_DRY_RUN_TTL_EXPIRED")
    metadata = {
        "schema": "persona_dream.phase11_provider_metadata_bundle.v1",
        "status": "PASS_PHASE11_PROVIDER_METADATA_DRY_RUN" if not metadata_blockers else "BLOCKED_PHASE11_PROVIDER_METADATA",
        "provider_id": provider,
        "endpoint": endpoint,
        "revision_id": revision_id,
        "source_urls": source_urls,
        "source_retrieved_at": schema_generated,
        "source_content_sha256": sha256_file(schema_receipt_path),
        "normalized_schema_sha256": "sha256:" + hashlib.sha256(schema_payload).hexdigest(),
        "dry_run_expires_at": dry_expires.isoformat(),
        "live_expires_at": live_expires.isoformat(),
        "dry_run_ttl_hours": 168,
        "live_ttl_hours": 24,
        "fal_preflight_sha256": sha256_file(fal_preflight_path),
        "pricing_evidence_status": "UNVERIFIED_LIVE_PRICE",
        "entitlement_evidence_status": "KEY_PRESENT_NOT_GENERATION_ENTITLEMENT",
        "async_strategy": {
            "mode": "polling",
            "task_id_mapping": "provider response request_id/task_id",
            "terminal_states": ["completed", "failed", "cancelled"],
            "timeout_seconds": 900,
            "cancellation_policy": "no retry or fallback in first canary",
        },
        "blockers": metadata_blockers,
        "actual_provider_call_attempts": 0,
        "generation_call_started": False,
        "queue_submit_started": False,
        "provider_live": False,
    }
    payload_hash = sha256_file(phase10_receipt_path)
    media_hash = sha256_file(media_manifest_path)
    metadata_hash = "sha256:" + hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
    approval_bindings = {
        "revision_id": revision_id,
        "provider_id": provider,
        "endpoint": endpoint,
        "payload_sha256": payload_hash,
        "media_requirement_manifest_sha256": media_hash,
        "provider_metadata_sha256": metadata_hash,
    }
    approvals = {
        "schema": "persona_dream.phase11_approval_state_receipt.v1",
        "status": "PASS_PHASE11_APPROVAL_CONTRACTS_DRY_RUN",
        "bindings": approval_bindings,
        "payload_acceptance": "DRAFT_NOT_APPROVAL",
        "asset_approval": "DRAFT_NOT_APPROVAL",
        "cost_approval": "DRAFT_NOT_APPROVAL",
        "paid_call_authorization": "NOT_REQUESTED",
        "manual_payload_accepted": False,
        "assets_approved": False,
        "cost_approved": False,
        "paid_call_authorized": False,
        "live_submission_allowed": False,
        "expires_at": None,
        "approved_by": None,
    }
    dry_blockers: list[str] = []
    if phase10.get("status") != "PASS_PHASE10_PROVIDER_CONTRACT_DRY_RUN_WITH_LIVE_BLOCKERS":
        dry_blockers.append("BLOCKED_PHASE10_CONTRACT")
    if media.get("status") != "PASS_PHASE11_MEDIA_REQUIREMENTS_DRY_RUN":
        dry_blockers.append("BLOCKED_PHASE11_MEDIA_REQUIREMENTS")
    if metadata["status"] != "PASS_PHASE11_PROVIDER_METADATA_DRY_RUN":
        dry_blockers.append("BLOCKED_PHASE11_PROVIDER_METADATA")
    forbidden_true = {
        "manual_payload_accepted": approvals["manual_payload_accepted"],
        "assets_approved": approvals["assets_approved"],
        "cost_approved": approvals["cost_approved"],
        "paid_call_authorized": approvals["paid_call_authorized"],
        "publication_performed": media.get("publication_performed"),
        "provider_accessible_url_created": media.get("provider_accessible_url_created"),
    }
    dry_blockers.extend(f"BLOCKED_FORBIDDEN_DRY_RUN_STATE:{key}" for key, value in forbidden_true.items() if value is not False)
    if any(int(item.get("actual_provider_call_attempts") or 0) != 0 for item in (phase10, media, metadata)):
        dry_blockers.append("BLOCKED_PROVIDER_CALL_ATTEMPT_NONZERO")
    gate = {
        "schema": "persona_dream.phase11_submit_gate_receipt.v1",
        "status": "PASS_PHASE11_SUBMIT_GATE_DRY_RUN" if not dry_blockers else "BLOCKED_PHASE11_SUBMIT_GATE_DRY_RUN",
        "revision_id": revision_id,
        "provider_id": provider,
        "endpoint": endpoint,
        "dry_run_contract_status": "PASS" if not dry_blockers else "BLOCKED",
        "live_submit_status": "BLOCKED_PHASE11_LIVE_SUBMIT",
        "actual_provider_call_attempts": 0,
        "generation_call_started": False,
        "provider_live": False,
        "provider_accessible_url_created": False,
        "publication_performed": False,
        "manual_payload_accepted": False,
        "assets_approved": False,
        "cost_approved": False,
        "paid_call_authorized": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "dry_run_blockers": dry_blockers,
        "live_blockers": [
            "BLOCKED_PROVIDER_ACCESSIBLE_URLS_MISSING",
            "BLOCKED_MANUAL_PAYLOAD_ACCEPTANCE_MISSING",
            "BLOCKED_ASSET_APPROVAL_MISSING",
            "BLOCKED_COST_APPROVAL_MISSING",
            "BLOCKED_PAID_CALL_AUTHORIZATION_MISSING",
            "BLOCKED_PROVIDER_LIVE_CANARY_MISSING",
        ],
        "input_hashes": {
            "phase10_contract": payload_hash,
            "media_requirements": media_hash,
            "provider_metadata": metadata_hash,
        },
        "claims": {
            "proves": ["local Phase 11 contracts agree and forbidden side effects are zero"] if not dry_blockers else [],
            "does_not_prove": ["public media", "approval", "payment", "provider readiness", "submission", "returned video"],
        },
    }
    return metadata, approvals, gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase10-contract", type=Path, required=True)
    parser.add_argument("--schema-receipt", type=Path, required=True)
    parser.add_argument("--fal-preflight", type=Path, required=True)
    parser.add_argument("--media-manifest", type=Path, required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    metadata, approvals, gate = build_bundle(args.phase10_contract, args.schema_receipt, args.fal_preflight, args.media_manifest, args.revision_id)
    write_object(args.output_root / "phase11_provider_metadata_bundle.json", metadata)
    write_object(args.output_root / "phase11_approval_state_receipt.json", approvals)
    write_object(args.output_root / "phase11_submit_gate_receipt.json", gate)
    print(json.dumps(gate, indent=2, sort_keys=True) if args.json else gate["status"])
    return 0 if gate["status"] == "PASS_PHASE11_SUBMIT_GATE_DRY_RUN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
