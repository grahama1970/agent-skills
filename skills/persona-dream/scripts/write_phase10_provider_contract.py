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


def read_json_if_exists(path: Path | None) -> dict[str, Any]:
    if path and path.is_file():
        return read_json(path)
    return {}


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


def string_value(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


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
                    "panel_id": asset.get("panel_id"),
                    "frame_role": asset.get("frame_role"),
                    "local_path": asset.get("path"),
                    "width": asset.get("width"),
                    "height": asset.get("height"),
                    "time_s": asset.get("time_s"),
                    "identity_continuity_status": asset.get("identity_continuity_status"),
                    "media_lock_status": asset.get("status"),
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


def selected_provider_best_practice(packet: dict[str, Any]) -> dict[str, Any]:
    provider_id = str(packet.get("provider_id") or "")
    if provider_id == "kling":
        skill_path = Path(__file__).resolve().parents[1] / ".." / "best-practices-kling-scene" / "SKILL.md"
        skill_path = skill_path.resolve()
        return {
            "provider_id": provider_id,
            "status": "SELECTED_PROVIDER_BEST_PRACTICE_BOUND",
            "skill": "best-practices-kling-scene",
            "path": str(skill_path),
            "sha256": sha256_file(skill_path) if skill_path.is_file() else None,
            "required_sections": [
                "Core Rule",
                "Scene Packet Schema",
                "Provider Payload Template",
                "Omni Prompting Rules",
                "Cinematography Control Matrix",
                "Multi-Shot Rules",
                "Voice And Audio Rules",
                "API Execution Rules",
                "Review Page Requirements",
                "Minimum Acceptance Gate",
            ],
        }
    return {
        "provider_id": provider_id or None,
        "status": "GENERIC_PROVIDER_REGISTRY_CONTRACT_BOUND",
        "skill": "provider_registry_current_docs",
        "path": None,
        "sha256": None,
        "required_sections": [
            "selected endpoint schema",
            "accepted input modalities",
            "duration limits",
            "reference support",
            "policy blockers",
        ],
    }


def infer_run_root_from_media_lock(media_lock_path: Path | None) -> Path | None:
    if not media_lock_path:
        return None
    for parent in media_lock_path.parents:
        if parent.name == "pipeline-complete" or (parent / "phase_06_script").exists():
            return parent
    return media_lock_path.parent.parent if media_lock_path.parent.name.startswith("phase_") else media_lock_path.parent


def source_path(packet: dict[str, Any], media_lock_path: Path | None, key: str, candidates: list[str]) -> Path | None:
    raw = string_value(packet.get(key))
    if raw:
        path = Path(raw)
        if path.is_file():
            return path
    run_root = infer_run_root_from_media_lock(media_lock_path)
    if not run_root:
        return None
    for candidate in candidates:
        path = run_root / candidate
        if path.is_file():
            return path
    return None


def panel_number(panel_id: str) -> int:
    digits = "".join(ch for ch in panel_id if ch.isdigit())
    return int(digits) if digits else 0


def normalize_panel_id(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if value.startswith("sb_"):
        return value
    digits = "".join(ch for ch in value if ch.isdigit())
    return f"sb_{int(digits):03d}" if digits else value


def media_assets_by_panel(media_plan: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    assets = media_plan.get("assets") if isinstance(media_plan.get("assets"), list) else []
    by_panel: dict[str, dict[str, dict[str, Any]]] = {}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        panel_id = normalize_panel_id(asset.get("panel_id"))
        if not panel_id and isinstance(asset.get("asset_id"), str):
            panel_id = normalize_panel_id(str(asset["asset_id"]).split(".")[0])
        frame_role = str(asset.get("frame_role") or "")
        if not panel_id or frame_role not in {"start_frame", "end_frame"}:
            continue
        by_panel.setdefault(panel_id, {})[frame_role] = asset
    return by_panel


def storyboard_panels_by_id(storyboard: dict[str, Any]) -> dict[str, dict[str, Any]]:
    panels = storyboard.get("panels") if isinstance(storyboard.get("panels"), list) else []
    out: dict[str, dict[str, Any]] = {}
    for panel in panels:
        if not isinstance(panel, dict):
            continue
        panel_id = normalize_panel_id(panel.get("panel_id"))
        if panel_id:
            out[panel_id] = panel
    return out


def transcript_for_panel(script_contract: dict[str, Any], panel: dict[str, Any]) -> list[dict[str, Any]]:
    transcript = script_contract.get("timed_transcript")
    if not isinstance(transcript, list):
        return []
    time_range = panel.get("time_range") if isinstance(panel.get("time_range"), list) else []
    if len(time_range) != 2:
        return [line for line in transcript if isinstance(line, dict)]
    start, end = time_range
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return [line for line in transcript if isinstance(line, dict)]
    lines: list[dict[str, Any]] = []
    for line in transcript:
        if not isinstance(line, dict):
            continue
        line_start = line.get("start_s")
        line_end = line.get("end_s")
        if isinstance(line_start, (int, float)) and isinstance(line_end, (int, float)) and line_end >= start and line_start <= end:
            lines.append(line)
    return lines


def compact_prompt(*parts: Any) -> str:
    text = " ".join(str(part).strip() for part in parts if part)
    return " ".join(text.split())


def panel_time_range(panel: dict[str, Any], start_asset: dict[str, Any] | None, end_asset: dict[str, Any] | None) -> list[float | None]:
    raw = panel.get("time_range")
    if isinstance(raw, list) and len(raw) == 2:
        return [raw[0], raw[1]]
    return [start_asset.get("time_s") if start_asset else None, end_asset.get("time_s") if end_asset else None]


def build_panel_payloads(
    packet: dict[str, Any],
    media_plan: dict[str, Any],
    storyboard: dict[str, Any],
    script_contract: dict[str, Any],
    base_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    provider_input = base_payload.get("input") if isinstance(base_payload.get("input"), dict) else {}
    provider_id = str(packet.get("provider_id") or "unknown")
    scene_types = []
    scene_contract_path = Path(str(packet.get("scene_contract_path") or ""))
    scene_contract = read_json_if_exists(scene_contract_path if scene_contract_path.is_file() else None)
    if isinstance(scene_contract.get("classified_scene_types"), list):
        scene_types = [str(item) for item in scene_contract["classified_scene_types"]]

    assets = media_assets_by_panel(media_plan)
    panels = storyboard_panels_by_id(storyboard)
    panel_ids = sorted(set(assets) | set(panels), key=panel_number)
    payloads: list[dict[str, Any]] = []
    for panel_id in panel_ids:
        panel = panels.get(panel_id, {})
        start_asset = assets.get(panel_id, {}).get("start_frame")
        end_asset = assets.get(panel_id, {}).get("end_frame")
        time_range = panel_time_range(panel, start_asset, end_asset)
        start_s = time_range[0] if isinstance(time_range[0], (int, float)) else None
        end_s = time_range[1] if isinstance(time_range[1], (int, float)) else None
        duration = round(end_s - start_s, 3) if start_s is not None and end_s is not None and end_s > start_s else provider_input.get("duration")
        panel_lines = transcript_for_panel(script_contract, panel)
        dialogue = panel.get("dialogue")
        no_dialogue = dialogue in (None, "", []) or dialogue == "NO_DIALOGUE"
        voice_status = "NO_DIALOGUE" if no_dialogue else "VOICE_TEXT_ONLY_PROVIDER_ID_MISSING"
        source_action = panel.get("action") or provider_input.get("prompt") or "SOURCE_STORYBOARD_NOT_BOUND"
        source_camera = panel.get("camera") or {"status": "SOURCE_STORYBOARD_NOT_BOUND"}
        prompt = compact_prompt(
            f"Panel {panel_id}.",
            source_action,
            f"Camera: {json.dumps(source_camera, sort_keys=True)}" if isinstance(source_camera, dict) else source_camera,
            f"Acting beats: {'; '.join(str(beat) for beat in panel.get('acting_beats', []))}" if isinstance(panel.get("acting_beats"), list) else None,
            f"Dialogue: {dialogue}" if not no_dialogue else None,
            "Preserve accepted start/end frame identities, surf geography, reef safety, lineup etiquette, and physical continuity.",
        )
        provider_projection = {
            **base_payload,
            "input": {
                **provider_input,
                "duration": duration,
                "end_frame_asset_id": end_asset.get("asset_id") if end_asset else f"{panel_id}.end_frame",
                "end_image_url": end_asset.get("provider_accessible_url") if end_asset else None,
                "image_url": start_asset.get("provider_accessible_url") if start_asset else None,
                "prompt": prompt,
                "start_frame_asset_id": start_asset.get("asset_id") if start_asset else f"{panel_id}.start_frame",
            },
            "submitted": False,
        }
        payloads.append(
            {
                "panel_id": panel_id,
                "provider_id": provider_id,
                "selected_provider_best_practice": "best-practices-kling-scene" if provider_id == "kling" else "provider_registry_current_docs",
                "source_evidence": {
                    "action": source_action,
                    "dialogue": dialogue,
                    "voice_status": voice_status,
                    "camera": source_camera,
                    "lighting": panel.get("lighting"),
                    "acting_beats": panel.get("acting_beats", []),
                    "required_entities": panel.get("required_entities") or panel.get("required_identities") or [],
                    "references": panel.get("references", []),
                    "time_range": time_range,
                    "transcript_lines": panel_lines,
                },
                "accepted_start_frame": start_asset,
                "accepted_end_frame": end_asset,
                "distillation": {
                    "scene_types": scene_types,
                    "provider_scene_type": packet.get("packet_kind"),
                    "duration": duration,
                    "aspect_ratio": provider_input.get("aspect_ratio"),
                    "audio_strategy": "TEXT_ONLY_DIALOGUE_BLOCKED_FOR_PROVIDER_VOICE_ID" if not no_dialogue else "NO_DIALOGUE",
                    "voice_status": voice_status,
                    "provider_prompt": prompt,
                    "negative_constraints": [
                        "do not change accepted character identities",
                        "do not invent provider-accessible URLs",
                        "do not imply live submission",
                        "do not treat local file paths as upload URLs",
                    ],
                },
                "provider_payload_projection": provider_projection,
                "live_blockers": LIVE_BLOCKERS,
                "non_claims": [
                    "panel payload projection was not submitted",
                    "local frame paths are not provider-accessible URLs",
                    "voice text is not a provider voice id",
                ],
            }
        )
    return payloads


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

    media_plan = media_publication_plan(packet)
    media_lock_raw = str(packet.get("media_lock_path") or "")
    media_lock_path = Path(media_lock_raw) if media_lock_raw else None
    storyboard_packet_path = source_path(
        packet,
        media_lock_path,
        "storyboard_packet_path",
        [
            "phase_07_storyboard_live_tau/storyboard_packet.json",
            "phase_07_storyboard/storyboard_packet.json",
        ],
    )
    script_contract_path = source_path(
        packet,
        media_lock_path,
        "script_contract_path",
        [
            "phase_06_script/script_contract.json",
        ],
    )
    storyboard_packet = read_json_if_exists(storyboard_packet_path)
    script_contract = read_json_if_exists(script_contract_path)
    panel_payloads = build_panel_payloads(packet, media_plan, storyboard_packet, script_contract, payload)

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
    gate_receipt_path = output_root / "phase10_provider_contract_dry_run_gate_receipt.json"

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
        "selected_provider_best_practice": selected_provider_best_practice(packet),
        "distillation_source_paths": {
            "storyboard_packet_path": str(storyboard_packet_path) if storyboard_packet_path else None,
            "storyboard_packet_sha256": sha256_file(storyboard_packet_path) if storyboard_packet_path else None,
            "script_contract_path": str(script_contract_path) if script_contract_path else None,
            "script_contract_sha256": sha256_file(script_contract_path) if script_contract_path else None,
            "media_lock_path": str(media_lock_path) if media_lock_path else None,
            "media_lock_sha256": sha256_file(media_lock_path) if media_lock_path and media_lock_path.is_file() else None,
        },
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
        "provider_media_publication_plan": media_plan,
        "panel_payloads": panel_payloads,
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
    gate_receipt = {
        "schema": "persona_dream.phase10.provider_contract_dry_run_gate_receipt.v1",
        "generated_at": generated_at,
        "status": "PASS_PHASE10_PROVIDER_CONTRACT_DRY_RUN_GATE" if status == PASS_STATUS else "BLOCKED_PHASE10_PROVIDER_CONTRACT_DRY_RUN_GATE",
        "contract_path": str(contract_path),
        "contract_sha256": receipt["contract_sha256"],
        "contract_receipt_path": str(receipt_path),
        "contract_receipt_sha256": sha256_file(receipt_path),
        "phase10_contract_status": status,
        "phase10_contract_blockers": phase10_blockers,
        "phase11_live_readiness_blockers": LIVE_BLOCKERS,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "mocked": False,
        "proof_kind": "local_dry_run_contract_gate",
        "fixture_backed": True,
        "live_external_evidence": False,
        "mocked_provider_response": False,
        "claims": {
            "proves": [
                "the Phase 10 provider contract was emitted for local inspection",
                "the contract receipt is bound by path and sha256",
                "live-readiness blockers are retained",
                "no provider request was submitted",
            ],
            "does_not_prove": [
                "current fal provider schema compatibility",
                "provider-accessible media URLs",
                "URL probe success",
                "cost approval",
                "provider entitlement",
                "manual acceptance",
                "paid-call authorization",
                "live provider readiness",
                "live video generation",
                "provider return",
                "Watch observation",
                "memory persistence",
            ],
        },
    }
    write_json(gate_receipt_path, gate_receipt)
    receipt["gate_receipt_path"] = str(gate_receipt_path)
    receipt["gate_receipt_sha256"] = sha256_file(gate_receipt_path)
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
