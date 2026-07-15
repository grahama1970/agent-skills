#!/usr/bin/env python3
"""Fail closed for the superseded free-form Phase 11 dry-run writer.

The canonical boundary is now compiled by compile_phase11_canonical_live_request.py
and independently checked by validate_phase11_canonical_live_request.py.  This
legacy command remains only so old automation cannot silently emit a false-green
PASS from a free-form revision id or a receipt-file hash.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def build_bundle(
    phase10_receipt_path: Path,
    schema_receipt_path: Path,
    fal_preflight_path: Path,
    media_manifest_path: Path,
    revision_id: str,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    blockers = [
        "BLOCKED_LEGACY_PHASE11_BUNDLE_SUPERSEDED",
        "BLOCKED_LEGACY_FREE_FORM_REVISION_ID",
        "BLOCKED_LEGACY_PAYLOAD_HASHES_RECEIPT_NOT_REQUEST_BODY",
        "BLOCKED_LEGACY_MEDIA_MANIFEST_V1",
        "BLOCKED_ACTIVE_CONSISTENT_ACTIVATION_NOT_BOUND",
    ]
    metadata = {
        "schema": "persona_dream.phase11_legacy_bundle_blocker.v1",
        "status": "BLOCKED_PROVIDER_GATE",
        "revision_id": revision_id,
        "blockers": blockers,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "submitted": False,
    }
    approvals = {
        "schema": "persona_dream.phase11_legacy_approval_state.v1",
        "status": "BLOCKED_PROVIDER_GATE",
        "required_approval_receipts": [
            "publication_authorization",
            "visual_media_acceptance",
            "exact_request_acceptance",
            "cost_acceptance",
            "paid_call_authorization",
        ],
        "blockers": blockers,
        "actual_provider_call_attempts": 0,
    }
    gate = {
        "schema": "persona_dream.phase11_legacy_submit_gate.v1",
        "status": "BLOCKED_PROVIDER_GATE",
        "revision_id": revision_id,
        "technical_blockers": blockers,
        "missing_approval_types": [],
        "actual_provider_call_attempts": 0,
        "generation_call_started": False,
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "claims": {
            "proves": ["legacy Phase 11 automation cannot emit a canonical PASS"],
            "does_not_prove": ["Phase 11 technical readiness", "approval", "provider submission"],
        },
    }
    return metadata, approvals, gate


def write_object(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    metadata, approvals, gate = build_bundle(
        args.phase10_contract,
        args.schema_receipt,
        args.fal_preflight,
        args.media_manifest,
        args.revision_id,
    )
    write_object(args.output_root / "phase11_provider_metadata_bundle.json", metadata)
    write_object(args.output_root / "phase11_approval_state_receipt.json", approvals)
    write_object(args.output_root / "phase11_submit_gate_receipt.json", gate)
    print(json.dumps(gate, indent=2, sort_keys=True) if args.json else gate["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
