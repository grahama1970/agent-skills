#!/usr/bin/env python3
"""Write dry-run provider-specific video packets from a provider scorecard."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_VIDEO_PROVIDER_PACKET_DRY_RUN"
BLOCKED_STATUS = "BLOCKED_VIDEO_PROVIDER_PACKET"
PACKET_SCHEMA = "persona-dream.video-provider-packet.v1"
MAPPING_SCHEMA = "persona_dream.video_provider_payload_mapping_receipt.v1"

FAL_ROUTES = {
    "kling": {
        "provider_route": "fal-kling",
        "fal_model_endpoint": "fal-ai/kling-video/v3/pro/image-to-video",
        "packet_kind": "fal_kling_image_to_video",
    },
    "bytedance-seedance": {
        "provider_route": "fal-seedance",
        "fal_model_endpoint": "bytedance/seedance-2.0/text-to-video",
        "packet_kind": "fal_seedance_multimodal_text_to_video",
    },
}


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


def add_blocker(blockers: list[str], blocker: str) -> None:
    if blocker not in blockers:
        blockers.append(blocker)


def scene_prompt(scene_contract: dict[str, Any]) -> str:
    scene_types = ", ".join(scene_contract.get("classified_scene_types") or [])
    caps = scene_contract.get("required_capabilities") if isinstance(scene_contract.get("required_capabilities"), dict) else {}
    duration = caps.get("duration_seconds", 10)
    return (
        f"Dry-run Persona Dream video scene {scene_contract.get('scene_id')}: "
        f"{scene_types}. Duration target {duration}s. Preserve accepted storyboard identity, "
        "camera, motion, and negative constraints from upstream packet."
    )


def media_assets(media_lock: dict[str, Any]) -> list[dict[str, Any]]:
    raw = media_lock.get("assets")
    return raw if isinstance(raw, list) else []


def first_asset_id(media_lock: dict[str, Any], role: str) -> str | None:
    for asset in media_assets(media_lock):
        if isinstance(asset, dict) and asset.get("frame_role") == role:
            return str(asset.get("asset_id"))
    return None


def provider_payload(provider_id: str, scene_contract: dict[str, Any], media_lock: dict[str, Any]) -> dict[str, Any]:
    caps = scene_contract.get("required_capabilities") if isinstance(scene_contract.get("required_capabilities"), dict) else {}
    prompt = scene_prompt(scene_contract)
    duration = caps.get("duration_seconds", 10)
    if provider_id == "kling":
        return {
            "model": FAL_ROUTES[provider_id]["fal_model_endpoint"],
            "input": {
                "prompt": prompt,
                "duration": duration,
                "image_url": None,
                "end_image_url": None,
                "start_frame_asset_id": first_asset_id(media_lock, "start_frame"),
                "end_frame_asset_id": first_asset_id(media_lock, "end_frame"),
                "aspect_ratio": caps.get("aspect_ratio", "16:9"),
            },
            "submitted": False,
        }
    if provider_id == "bytedance-seedance":
        return {
            "model": FAL_ROUTES[provider_id]["fal_model_endpoint"],
            "input": {
                "prompt": prompt,
                "duration": duration,
                "reference_assets": [asset.get("asset_id") for asset in media_assets(media_lock) if isinstance(asset, dict)],
                "audio_required": bool(caps.get("native_audio") or caps.get("audio_video_sync")),
                "provider_accessible_urls": [],
            },
            "submitted": False,
        }
    return {}


def write_provider_packet(
    scene_contract_path: Path,
    scorecard_path: Path,
    media_lock_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    scene_contract = read_json(scene_contract_path)
    scorecard = read_json(scorecard_path)
    media_lock = read_json(media_lock_path)
    output_root.mkdir(parents=True, exist_ok=True)
    packet_path = output_root / "video_provider_packet.json"
    mapping_path = output_root / "provider_payload_mapping_receipt.json"
    blockers: list[str] = []

    provider_id = str(scorecard.get("recommended_provider_id") or "NO_PROVIDER_SELECTED")
    if scorecard.get("selection_status") != "PASS_PROVIDER_SELECTION_DRY_RUN_ONLY":
        add_blocker(blockers, "BLOCKED_PROVIDER_SELECTION_NOT_PASS")
    if scorecard.get("provider_registry_refresh_status") != "PASS_PROVIDER_REGISTRY_REFRESH":
        add_blocker(blockers, "BLOCKED_PROVIDER_REGISTRY_REFRESH_NOT_PASS")
    if provider_id not in FAL_ROUTES:
        add_blocker(blockers, "BLOCKED_PROVIDER_PACKET_ROUTE_UNSUPPORTED")
    if provider_id not in set(scorecard.get("provider_registry_refresh_fal_api_doc_provider_ids") or []):
        add_blocker(blockers, f"BLOCKED_FAL_API_DOCS_NOT_OBSERVED:{provider_id}")
    if scorecard.get("provider_live") is not False or scorecard.get("paid_call_authorized") is not False:
        add_blocker(blockers, "BLOCKED_PROVIDER_LIVE_OR_PAID_IN_DRY_RUN")
    if not media_assets(media_lock):
        add_blocker(blockers, "BLOCKED_MEDIA_LOCK_ASSETS_MISSING")

    route = FAL_ROUTES.get(provider_id, {})
    payload = provider_payload(provider_id, scene_contract, media_lock) if not blockers else {}
    status = PASS_STATUS if not blockers else BLOCKED_STATUS
    generated_at = datetime.now(timezone.utc).isoformat()

    packet = {
        "schema_version": PACKET_SCHEMA,
        "generated_at": generated_at,
        "status": status,
        "provider_id": provider_id,
        "provider_route": route.get("provider_route"),
        "packet_kind": route.get("packet_kind"),
        "fal_model_endpoint": route.get("fal_model_endpoint"),
        "run_id": scene_contract.get("run_id"),
        "revision_id": scene_contract.get("revision_id"),
        "scene_id": scene_contract.get("scene_id"),
        "scene_contract_path": str(scene_contract_path),
        "scene_contract_sha256": sha256_file(scene_contract_path),
        "video_provider_scorecard_path": str(scorecard_path),
        "video_provider_scorecard_sha256": sha256_file(scorecard_path),
        "media_lock_path": str(media_lock_path),
        "media_lock_sha256": sha256_file(media_lock_path),
        "provider_payload": payload,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "external_task_id": None,
        "provider_ready": False,
        "live_submit_ready": False,
        "blockers": blockers,
        "claims": {
            "proves": [
                "provider-specific dry-run packet was written from a scorecard, scene contract, and media lock",
                "no provider, paid, URL, submit, or live-ready state was claimed",
            ],
            "does_not_prove": [
                "current fal provider schema compatibility",
                "provider-accessible media URLs",
                "paid-call authorization",
                "manual acceptance",
                "live provider readiness",
                "live video generation",
            ],
        },
    }
    mapping = {
        "schema": MAPPING_SCHEMA,
        "generated_at": generated_at,
        "status": status,
        "provider_id": provider_id,
        "provider_route": route.get("provider_route"),
        "fal_model_endpoint": route.get("fal_model_endpoint"),
        "request_body_path": str(packet_path),
        "submitted": False,
        "external_task_id": None,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "blockers": blockers,
        "claims": packet["claims"],
    }
    write_json(packet_path, packet)
    write_json(mapping_path, mapping)
    return {
        "status": status,
        "packet_path": str(packet_path),
        "provider_payload_mapping_receipt_path": str(mapping_path),
        "provider_id": provider_id,
        "provider_route": route.get("provider_route"),
        "blockers": blockers,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-contract", required=True, type=Path)
    parser.add_argument("--scorecard", required=True, type=Path)
    parser.add_argument("--media-lock", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = write_provider_packet(
        args.scene_contract.resolve(),
        args.scorecard.resolve(),
        args.media_lock.resolve(),
        args.output_root.resolve(),
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] in {PASS_STATUS, BLOCKED_STATUS} else 1


if __name__ == "__main__":
    raise SystemExit(main())
