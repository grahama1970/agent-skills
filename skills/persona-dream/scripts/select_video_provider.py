#!/usr/bin/env python3
"""Select a dry-run video provider for a provider-neutral scene contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PROVIDER_SELECTION_DRY_RUN_ONLY"
BLOCKED_NO_PROVIDER = "BLOCKED_NO_ELIGIBLE_PROVIDER"
BLOCKED_POLICY = "BLOCKED_PROVIDER_POLICY"
SCENE_SCHEMA = "persona-dream.video-scene-classifier.v1"
SCORECARD_SCHEMA = "persona-dream.video-provider-scorecard.v1"

CAPABILITY_WEIGHTS = {
    "image_to_video": 20,
    "text_to_video": 8,
    "first_last_frame_control": 20,
    "identity_reference_support": 15,
    "multi_character_consistency": 10,
    "motion_quality": 15,
    "cinematic_camera_control": 10,
    "native_audio": 20,
    "audio_video_sync": 20,
    "multi_reference_inputs": 20,
    "reference_video_motion_control": 12,
    "local_low_cost_preview": 25,
    "dialogue_audio": 18,
    "sound_effects": 12,
    "world_consistency": 16,
    "object_location_consistency": 16,
    "reusable_character_assets": 18,
    "natural_motion": 18,
    "environment_establishing_shot": 12,
    "stylized_effects": 18,
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


def required_capabilities(scene: dict[str, Any]) -> dict[str, Any]:
    raw = scene.get("required_capabilities")
    return raw if isinstance(raw, dict) else {}


def policy_constraints(scene: dict[str, Any]) -> dict[str, Any]:
    raw = scene.get("policy_constraints")
    return raw if isinstance(raw, dict) else {}


def score_provider(provider: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any]:
    required = required_capabilities(scene)
    policy = policy_constraints(scene)
    capabilities = provider.get("capabilities") if isinstance(provider.get("capabilities"), dict) else {}
    provider_policy = provider.get("policy") if isinstance(provider.get("policy"), dict) else {}
    blockers: list[str] = []
    fit: dict[str, int] = {}
    score = 0

    for capability, required_value in required.items():
        if capability in {"duration_seconds", "aspect_ratio", "provider_accessible_urls_required"}:
            continue
        if required_value is not True:
            continue
        weight = CAPABILITY_WEIGHTS.get(capability, 5)
        if capabilities.get(capability) is True:
            fit[capability] = weight
            score += weight
        else:
            fit[capability] = 0
            add_blocker(blockers, "BLOCKED_PROVIDER_CAPABILITY_MISSING")

    duration = required.get("duration_seconds")
    max_duration = capabilities.get("duration_max_seconds")
    if isinstance(duration, (int, float)) and isinstance(max_duration, (int, float)):
        if duration <= max_duration:
            fit["duration_fit"] = 10
            score += 10
        else:
            fit["duration_fit"] = 0
            add_blocker(blockers, "BLOCKED_PROVIDER_CAPABILITY_MISSING")

    if provider_policy.get("heightened_copyright_review_required") is True or policy.get("ip_risk_review_required") is True:
        if provider["provider_id"] == "bytedance-seedance" or policy.get("ip_risk_review_required") is True:
            add_blocker(blockers, "BLOCKED_HEIGHTENED_COPYRIGHT_REVIEW_REQUIRED")

    if policy.get("manual_acceptance_required") is True:
        add_blocker(blockers, "BLOCKED_MANUAL_ACCEPTANCE_MISSING")
    if policy.get("provider_live") is not True:
        add_blocker(blockers, "BLOCKED_PROVIDER_LIVE_NOT_ENABLED")
    if policy.get("paid_call_authorized") is not True:
        add_blocker(blockers, "BLOCKED_PAID_CALL_AUTHORIZATION_MISSING")
    if provider_policy.get("live_schema_verified") is not True:
        add_blocker(blockers, "BLOCKED_PROVIDER_SCHEMA_UNVERIFIED")
    if required.get("provider_accessible_urls_required") is True and provider_policy.get("provider_accessible_urls_required") is True:
        add_blocker(blockers, "BLOCKED_PROVIDER_ACCESSIBLE_URLS_MISSING")

    capability_blocked = "BLOCKED_PROVIDER_CAPABILITY_MISSING" in blockers
    policy_blockers = [blocker for blocker in blockers if blocker != "BLOCKED_PROVIDER_CAPABILITY_MISSING"]
    return {
        "provider_id": provider.get("provider_id"),
        "eligible_for_dry_run": not capability_blocked,
        "eligible_for_live_submit": False,
        "score": score,
        "priority": int(provider.get("priority", 999)),
        "fit": fit,
        "blockers": blockers,
        "policy_blocked": bool(policy_blockers),
        "recommended_for": provider.get("recommended_for") if isinstance(provider.get("recommended_for"), list) else [],
        "hosting_routes": provider.get("hosting_routes") if isinstance(provider.get("hosting_routes"), list) else [],
        "evidence_sources": provider.get("evidence_sources") if isinstance(provider.get("evidence_sources"), list) else [],
    }


def select_provider(scene: dict[str, Any], registry: dict[str, Any], scene_path: Path, registry_path: Path, output: Path) -> dict[str, Any]:
    blockers: list[str] = []
    if scene.get("schema_version") != SCENE_SCHEMA:
        add_blocker(blockers, "BLOCKED_VIDEO_SCENE_CONTRACT_SCHEMA")
    if registry.get("schema_version") != "persona-dream.video-provider-registry.v1":
        add_blocker(blockers, "BLOCKED_PROVIDER_REGISTRY_SCHEMA")
    if registry.get("status") != "CURRENT":
        add_blocker(blockers, "BLOCKED_PROVIDER_REGISTRY_STALE")

    provider_scores = [
        score_provider(provider, scene)
        for provider in registry.get("providers", [])
        if isinstance(provider, dict) and provider.get("provider_id")
    ]
    eligible = [provider for provider in provider_scores if provider["eligible_for_dry_run"]]
    if not eligible:
        recommended = "NO_PROVIDER_SELECTED"
        selection_status = BLOCKED_NO_PROVIDER
        add_blocker(blockers, "BLOCKED_PROVIDER_CAPABILITY_MISSING")
    else:
        ranked = sorted(eligible, key=lambda item: (-item["score"], item["priority"], str(item["provider_id"])))
        top = ranked[0]
        recommended = str(top["provider_id"])
        policy_blocked = any(provider["provider_id"] == recommended and provider["policy_blocked"] for provider in provider_scores)
        selection_status = BLOCKED_POLICY if policy_blocked and recommended == "NO_PROVIDER_SELECTED" else PASS_STATUS

    if registry.get("status") != "CURRENT":
        selection_status = BLOCKED_POLICY

    scorecard = {
        "schema_version": SCORECARD_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": scene.get("run_id"),
        "revision_id": scene.get("revision_id"),
        "scene_id": scene.get("scene_id"),
        "scene_contract_path": str(scene_path),
        "scene_contract_hash": sha256_file(scene_path),
        "provider_registry_path": str(registry_path),
        "provider_registry_hash": sha256_file(registry_path),
        "actual_provider_call_attempts": 0,
        "providers": provider_scores,
        "recommended_provider_id": recommended,
        "selection_status": selection_status,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "blockers": sorted(set(blockers)),
        "claims": {
            "proves": [
                "local dry-run provider selection was computed from scene requirements and a versioned registry",
            ],
            "does_not_prove": [
                "current provider schema compatibility",
                "provider-accessible URLs",
                "paid-call authorization",
                "manual acceptance",
                "live provider readiness",
                "live video generation",
            ],
        },
    }
    write_json(output, scorecard)
    return scorecard


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-contract", required=True, type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    registry_path = args.registry or Path(__file__).resolve().parents[1] / "provider_registry" / "video_provider_registry.v1.json"
    scorecard = select_provider(read_json(args.scene_contract), read_json(registry_path), args.scene_contract.resolve(), registry_path.resolve(), args.output.resolve())
    if args.json:
        print(json.dumps(scorecard, indent=2, sort_keys=True))
    else:
        print(scorecard["selection_status"])
    return 0 if scorecard["selection_status"] in {PASS_STATUS, BLOCKED_POLICY, BLOCKED_NO_PROVIDER} else 1


if __name__ == "__main__":
    raise SystemExit(main())
