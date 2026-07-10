#!/usr/bin/env python3
"""Compile a Phase 10 provider contract dry run.

Inputs are local Persona Dream artifacts only: a Phase 09 video provider packet
and a provider-registry refresh receipt. Outputs are an inspectable provider
contract and receipt that can later feed an authorized live submit gate.

Failure modes are fail-closed: malformed inputs, missing registry evidence,
submitted/live/paid flags, or missing payloads block the Phase 10 dry-run
contract. Live-readiness gaps such as public media URLs, cost approval, callback
configuration, manual acceptance, and paid authorization are retained as live
blockers without causing a local dry-run compile to submit anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PHASE10_PROVIDER_CONTRACT_DRY_RUN"
BLOCKED_STATUS = "BLOCKED_PHASE10_PROVIDER_CONTRACT"
CONTRACT_SCHEMA = "persona_dream.phase10.provider_contract.v1"
RECEIPT_SCHEMA = "persona_dream.phase10.provider_contract_receipt.v1"

LIVE_BLOCKERS = [
    "BLOCKED_PROVIDER_ACCESSIBLE_URLS_MISSING",
    "BLOCKED_PROVIDER_URL_PROBES_MISSING",
    "BLOCKED_COST_ESTIMATE_UNVERIFIED",
    "BLOCKED_PROVIDER_ENTITLEMENT_UNVERIFIED",
    "BLOCKED_MANUAL_ACCEPTANCE_MISSING",
    "BLOCKED_PAID_CALL_AUTHORIZATION_MISSING",
    "BLOCKED_LIVE_SUBMIT_DISABLED_IN_PHASE10_DRY_RUN",
]

NON_CLAIMS = [
    "does not prove current live fal schema compatibility",
    "does not prove provider-accessible media publication",
    "does not prove provider URL fetch behavior",
    "does not prove cost or entitlement",
    "does not prove manual acceptance",
    "does not prove paid authorization",
    "does not prove provider submission",
    "does not prove provider return",
    "does not prove Watch observation",
    "does not prove dream interpretation",
    "does not prove memory persistence",
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def sha256_json(data: Any) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def add_blocker(blockers: list[str], blocker: str) -> None:
    if blocker not in blockers:
        blockers.append(blocker)


def json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def normalized_request_schema(payload: dict[str, Any]) -> dict[str, Any]:
    model = payload.get("model")
    input_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    return {
        "status": "DRY_RUN_SCHEMA_DERIVED_FROM_LOCAL_PAYLOAD_AND_REGISTRY_EVIDENCE",
        "model_field": {
            "name": "model",
            "type": json_type(model),
            "required": True,
        },
        "input_fields": [
            {
                "name": key,
                "type": json_type(value),
                "required": value is not None,
                "value_present": value is not None and value != [],
            }
            for key, value in sorted(input_payload.items())
        ],
        "does_not_prove": [
            "provider accepted this schema today",
            "fal endpoint has not changed",
            "media URLs are fetchable by provider",
        ],
    }


def field_mapping(packet: dict[str, Any]) -> list[dict[str, Any]]:
    payload = packet.get("provider_payload") if isinstance(packet.get("provider_payload"), dict) else {}
    input_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    mapping = [
        {
            "provider_field": "model",
            "source": "video_provider_packet.fal_model_endpoint",
            "value": payload.get("model"),
            "status": "MAPPED",
        }
    ]
    for key, value in sorted(input_payload.items()):
        if key in {"image_url", "end_image_url", "provider_accessible_urls"}:
            source = "phase10.provider_media_publication_plan"
            status = "MAPPED_AS_LIVE_BLOCKER"
        elif key in {"start_frame_asset_id", "end_frame_asset_id", "reference_assets"}:
            source = "media_lock_manifest"
            status = "MAPPED"
        elif key in {"prompt", "duration", "aspect_ratio", "audio_required"}:
            source = "video_scene_contract"
            status = "MAPPED"
        else:
            source = "video_provider_packet.provider_payload.input"
            status = "MAPPED"
        mapping.append(
            {
                "provider_field": f"input.{key}",
                "source": source,
                "value_type": json_type(value),
                "value_present": value is not None and value != [],
                "status": status,
            }
        )
    return mapping


def media_publication_plan(packet: dict[str, Any]) -> dict[str, Any]:
    media_lock_raw = str(packet.get("media_lock_path") or "")
    media_lock_path = Path(media_lock_raw) if media_lock_raw else None
    assets: list[dict[str, Any]] = []
    if media_lock_path and media_lock_path.is_file():
        media_lock = read_json(media_lock_path)
        raw_assets = media_lock.get("assets") if isinstance(media_lock.get("assets"), list) else []
        for asset in raw_assets:
            if not isinstance(asset, dict):
                continue
            assets.append(
                {
                    "asset_id": asset.get("asset_id"),
                    "sha256": asset.get("sha256"),
                    "provider_accessible_url": asset.get("provider_accessible_url"),
                    "publication_status": "NOT_PUBLISHED_IN_PHASE10_DRY_RUN",
                    "url_probe_status": "NOT_RUN",
                    "live_blockers": [
                        "BLOCKED_PROVIDER_ACCESSIBLE_URLS_MISSING",
                        "BLOCKED_PROVIDER_URL_PROBES_MISSING",
                    ],
                }
        )
    return {
        "status": "DRY_RUN_MEDIA_PUBLICATION_PLAN_ONLY",
        "media_lock_path": str(media_lock_path) if media_lock_path else None,
        "asset_count": len(assets),
        "assets": assets,
        "provider_accessible_url_created": False,
        "url_probe_results": [],
        "live_blockers": [
            "BLOCKED_PROVIDER_ACCESSIBLE_URLS_MISSING",
            "BLOCKED_PROVIDER_URL_PROBES_MISSING",
        ],
    }


def build_contract(
    video_provider_packet_path: Path,
    registry_refresh_receipt_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    packet = read_json(video_provider_packet_path)
    registry_refresh = read_json(registry_refresh_receipt_path)
    phase10_blockers: list[str] = []

    if packet.get("status") != "PASS_VIDEO_PROVIDER_PACKET_DRY_RUN":
        add_blocker(phase10_blockers, "BLOCKED_VIDEO_PROVIDER_PACKET_NOT_PASS")
    if registry_refresh.get("status") != "PASS_PROVIDER_REGISTRY_REFRESH":
        add_blocker(phase10_blockers, "BLOCKED_PROVIDER_REGISTRY_REFRESH_NOT_PASS")
    if not isinstance(packet.get("provider_payload"), dict) or not packet.get("provider_payload"):
        add_blocker(phase10_blockers, "BLOCKED_PROVIDER_PAYLOAD_MISSING")
    if packet.get("provider_id") not in set(registry_refresh.get("fal_api_doc_provider_ids") or []):
        add_blocker(phase10_blockers, "BLOCKED_PHASE10_PROVIDER_ID_MISMATCH")
    for field in (
        "provider_live",
        "paid_call_authorized",
        "provider_accessible_url_created",
        "submitted",
        "provider_ready",
        "live_submit_ready",
    ):
        if packet.get(field) is not False:
            add_blocker(phase10_blockers, f"BLOCKED_{field.upper()}_IN_PHASE10_DRY_RUN")
    if packet.get("actual_provider_call_attempts", 0) != 0:
        add_blocker(phase10_blockers, "BLOCKED_ACTUAL_PROVIDER_CALL_ATTEMPTS_IN_PHASE10_DRY_RUN")
    if packet.get("external_task_id") is not None:
        add_blocker(phase10_blockers, "BLOCKED_EXTERNAL_TASK_ID_IN_PHASE10_DRY_RUN")

    payload = packet.get("provider_payload") if isinstance(packet.get("provider_payload"), dict) else {}
    if payload.get("model") and packet.get("fal_model_endpoint") and payload.get("model") != packet.get("fal_model_endpoint"):
        add_blocker(phase10_blockers, "BLOCKED_PHASE10_ENDPOINT_MISMATCH")
    if packet.get("provider_payload_sha256") and packet.get("provider_payload_sha256") != sha256_json(payload):
        add_blocker(phase10_blockers, "BLOCKED_PHASE10_PAYLOAD_HASH_MISMATCH")

    scorecard_path_raw = str(packet.get("video_provider_scorecard_path") or "")
    scorecard_path = Path(scorecard_path_raw) if scorecard_path_raw else None
    scorecard: dict[str, Any] = {}
    if scorecard_path and scorecard_path.is_file():
        scorecard = read_json(scorecard_path)
        if scorecard.get("recommended_provider_id") != packet.get("provider_id"):
            add_blocker(phase10_blockers, "BLOCKED_PHASE10_PROVIDER_ID_MISMATCH")
        for key, blocker in (
            ("run_id", "BLOCKED_PHASE10_RUN_LINEAGE_MISMATCH"),
            ("revision_id", "BLOCKED_PHASE10_REVISION_MISMATCH"),
            ("scene_id", "BLOCKED_PHASE10_RUN_LINEAGE_MISMATCH"),
        ):
            if scorecard.get(key) and packet.get(key) and scorecard.get(key) != packet.get(key):
                add_blocker(phase10_blockers, blocker)

    status = PASS_STATUS if not phase10_blockers else BLOCKED_STATUS
    generated_at = datetime.now(timezone.utc).isoformat()
    contract_path = output_root / "phase10_provider_contract.json"
    receipt_path = output_root / "phase10_provider_contract_receipt.json"

    contract = {
        "schema": CONTRACT_SCHEMA,
        "generated_at": generated_at,
        "status": status,
        "live_submit_status": "BLOCKED_LIVE_SUBMIT_PENDING_APPROVAL"
        if status == PASS_STATUS
        else "DRY_RUN_NOT_LIVE_SUBMITTABLE",
        "phase": "10_provider_contract",
        "provider_id": packet.get("provider_id"),
        "provider_route": packet.get("provider_route"),
        "fal_model_endpoint": packet.get("fal_model_endpoint"),
        "run_id": packet.get("run_id"),
        "revision_id": packet.get("revision_id"),
        "scene_id": packet.get("scene_id"),
        "video_provider_packet_path": str(video_provider_packet_path),
        "video_provider_packet_sha256": sha256_file(video_provider_packet_path),
        "registry_refresh_receipt_path": str(registry_refresh_receipt_path),
        "registry_refresh_receipt_sha256": sha256_file(registry_refresh_receipt_path),
        "registry_refresh_status": registry_refresh.get("status"),
        "registry_refresh_generated_at": registry_refresh.get("generated_at"),
        "registry_refresh_mode": registry_refresh.get("mode"),
        "registry_refresh_fal_api_doc_provider_ids": registry_refresh.get("fal_api_doc_provider_ids", []),
        "proof_kind": "fixture_contract_test",
        "fixture_backed": True,
        "live_external_evidence": False,
        "mocked_provider_response": False,
        "provider_request": {
            "status": "DRY_RUN_REQUEST_BODY_NOT_SUBMITTED",
            "body": payload,
            "payload_sha256": sha256_json(payload),
            "submitted": False,
            "external_task_id": None,
        },
        "normalized_request_schema": normalized_request_schema(payload),
        "field_mapping": field_mapping(packet),
        "provider_media_publication_plan": media_publication_plan(packet),
        "cost_contract": {
            "status": "DRY_RUN_COST_ESTIMATE_UNVERIFIED",
            "estimated_cost": None,
            "currency": None,
            "cost_ceiling": None,
            "paid_call_authorized": False,
            "live_blockers": [
                "BLOCKED_COST_ESTIMATE_UNVERIFIED",
                "BLOCKED_PAID_CALL_AUTHORIZATION_MISSING",
            ],
        },
        "entitlement_contract": {
            "status": "DRY_RUN_ENTITLEMENT_UNVERIFIED",
            "fal_api_key_observed": False,
            "provider_entitlement_verified": False,
            "live_blockers": ["BLOCKED_PROVIDER_ENTITLEMENT_UNVERIFIED"],
        },
        "async_return_contract": {
            "status": "DRY_RUN_ASYNC_PLAN_ONLY",
            "selected_async_mode": "polling",
            "polling_plan": {
                "enabled": True,
                "interval_s": 15,
                "max_attempts": 80,
                "accepted_for_phase10_dry_run": True,
                "task_id_source": "future_provider_submit_response.task_id",
                "terminal_states": ["COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"],
            },
            "callback_url": None,
            "callback_verified": False,
            "output_contract": {
                "expected_media_type": "video",
                "download_required": True,
                "ffprobe_required": True,
                "sha256_required": True,
            },
            "live_blockers": [],
        },
        "manual_acceptance": {
            "status": "MISSING",
            "accepted": False,
            "live_blockers": ["BLOCKED_MANUAL_ACCEPTANCE_MISSING"],
        },
        "phase10_contract_blockers": phase10_blockers,
        "phase11_live_readiness_blockers": LIVE_BLOCKERS,
        "dry_run_blockers": phase10_blockers,
        "live_call_blockers": LIVE_BLOCKERS,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "mocked": False,
        "non_claims": NON_CLAIMS,
        "claims": {
            "proves": [
                "Phase 09 provider packet was compiled into an inspectable Phase 10 provider contract",
                "the exact dry-run request body and payload hash were recorded",
                "registry refresh evidence was bound by path and sha256",
                "provider media publication, cost, entitlement, async return, manual acceptance, and paid authorization states are represented",
                "no provider request was submitted",
            ],
            "does_not_prove": [
                "current fal provider schema compatibility",
                "provider-accessible media URLs",
                "URL probe success",
                "cost approval",
                "provider entitlement",
                "callback readiness",
                "manual acceptance",
                "paid-call authorization",
                "live provider readiness",
                "live video generation",
                "Watch observation",
                "memory persistence",
            ],
        },
    }
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "generated_at": generated_at,
        "status": status,
        "contract_path": str(contract_path),
        "contract_sha256": sha256_json(contract),
        "video_provider_packet_path": str(video_provider_packet_path),
        "registry_refresh_receipt_path": str(registry_refresh_receipt_path),
        "provider_id": contract["provider_id"],
        "provider_route": contract["provider_route"],
        "fal_model_endpoint": contract["fal_model_endpoint"],
        "payload_sha256": contract["provider_request"]["payload_sha256"],
        "phase10_contract_blockers": phase10_blockers,
        "phase11_live_readiness_blockers": LIVE_BLOCKERS,
        "dry_run_blockers": phase10_blockers,
        "live_call_blockers": LIVE_BLOCKERS,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "mocked": False,
        "proof_kind": "fixture_contract_test",
        "fixture_backed": True,
        "live_external_evidence": False,
        "mocked_provider_response": False,
        "non_claims": NON_CLAIMS,
        "claims": contract["claims"],
    }
    write_json(contract_path, contract)
    receipt["contract_sha256"] = sha256_file(contract_path)
    write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-provider-packet", required=True, type=Path)
    parser.add_argument("--registry-refresh-receipt", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = build_contract(
        args.video_provider_packet.resolve(),
        args.registry_refresh_receipt.resolve(),
        args.output_root.resolve(),
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] in {PASS_STATUS, BLOCKED_STATUS} else 1


if __name__ == "__main__":
    raise SystemExit(main())
